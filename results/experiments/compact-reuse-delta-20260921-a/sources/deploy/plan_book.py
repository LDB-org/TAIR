"""Indexed, transactional storage for verified plans; no model inference here."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def search_terms(text):
    # Unicode words plus Han bigrams allow retrieval without whitespace in Chinese.
    words = re.findall(r'[^\W_]+', text.casefold())
    for run in re.findall(r'[\u3400-\u9fff]+', text):
        words.extend(run[i:i + 2] for i in range(len(run) - 1))
    return list(dict.fromkeys(words))


def checked(entry):
    entry = dict(entry)
    if entry['source_sha256'] != digest(entry['source']):
        raise ValueError('Corrupt codebook source')
    if entry['id'] != digest(entry['contract'] + '\0' + entry['source']):
        raise ValueError('Corrupt codebook identity')
    return entry


def ranked_entries(db, rows, batch_size):
    while batch := rows.fetchmany(batch_size):
        identities = [row['seq'] for row in batch]
        placeholders = ','.join('?' for _ in identities)
        entries = {row['seq']: row for row in db.execute(
            f'SELECT * FROM entries WHERE seq IN ({placeholders})', identities)}
        yield from (entries[identity] for identity in identities)
        # Widen only when the initial shortlist did not yield enough candidates.
        batch_size = 64


class PlanBook:
    """SQLite book with a 15-entry inference shortlist, independent of storage size.

    A legacy .json argument maps to a sibling .sqlite3 file. Original JSON and
    rejection files are imported once, transactionally, and never overwritten.
    """
    def __init__(self, path):
        supplied = Path(path)
        self.path = supplied.with_suffix('.sqlite3') if supplied.suffix == '.json' else supplied
        self.legacy = self.path.with_suffix('.json')

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version == 0:
                self.initialize(db)
            elif version != 1:
                raise ValueError('Unsupported book database version')
            with db:
                yield db
        finally:
            db.close()

    def initialize(self, db):
        # Serialize initialization and import, including simultaneous first use.
        db.execute('BEGIN IMMEDIATE')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version == 1:
            db.commit()
            return
        if version != 0:
            raise ValueError('Unsupported book database version')
        db.execute('''CREATE TABLE entries (
            seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, contract TEXT NOT NULL,
            source TEXT NOT NULL, source_sha256 TEXT NOT NULL, verification TEXT NOT NULL,
            entry_version INTEGER NOT NULL DEFAULT 1, successes INTEGER NOT NULL DEFAULT 1,
            reuse_count INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, last_used REAL NOT NULL)''')
        db.execute('''CREATE TABLE rejections (
            entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            contract_hash TEXT NOT NULL, PRIMARY KEY(entry_id, contract_hash))''')
        db.execute('CREATE VIRTUAL TABLE search USING fts5(terms)')
        db.execute('''CREATE TRIGGER delete_search AFTER DELETE ON entries BEGIN
            DELETE FROM search WHERE rowid=old.seq; END''')
        if self.legacy.exists():
            data = json.loads(self.legacy.read_text())
            if data['version'] != 1:
                raise ValueError('Unsupported book version')
            for raw in data['entries']:
                entry = checked(raw)
                self.insert(db, entry['contract'], entry['source'], entry['verification'])
            rejected = self.legacy.with_suffix('.rejected.json')
            if rejected.exists():
                for identity, contract_hash in json.loads(rejected.read_text()):
                    db.execute('''INSERT OR IGNORE INTO rejections SELECT id, ?
                        FROM entries WHERE id=?''', (contract_hash, identity))
        db.execute('PRAGMA user_version=1')
        db.commit()

    @staticmethod
    def validate_source(source):
        compile(source, '<admitted>', 'exec')

    @classmethod
    def insert(cls, db, contract, source, evidence):
        if not contract.strip() or not isinstance(evidence, str) or not evidence.strip():
            raise ValueError('Contract and verification evidence required')
        cls.validate_source(source)
        identity = digest(contract + '\0' + source)
        now = time.time()
        cursor = db.execute('''INSERT OR IGNORE INTO entries
            (id,contract,source,source_sha256,verification,created_at,last_used)
            VALUES (?,?,?,?,?,?,?)''', (identity, contract, source, digest(source), evidence, now, now))
        if cursor.rowcount:
            db.execute('INSERT INTO search(rowid,terms) VALUES (?,?)',
                       (cursor.lastrowid, ' '.join(search_terms(contract))))
            return identity
        db.execute('''UPDATE entries SET successes=successes+1, last_used=?, verification=?
            WHERE id=?''', (now, evidence, identity))
        return None

    def load(self):
        """Explicit full export/integrity check; never used by candidate retrieval."""
        if not self.path.exists() and not self.legacy.exists():
            return []
        with self.connection() as db:
            return [checked(row) for row in db.execute('SELECT * FROM entries ORDER BY seq')]

    def count(self):
        if not self.path.exists() and not self.legacy.exists():
            return 0
        with self.connection() as db:
            return db.execute('SELECT count(*) FROM entries').fetchone()[0]

    def admit(self, modules):
        """Call only after trusted verification of the complete plan."""
        with self.connection() as db:
            return [identity for contract, source, evidence in modules
                    if (identity := self.insert(db, contract, source, evidence))]

    def reject(self, entry_id, contract):
        with self.connection() as db:
            db.execute('''INSERT OR IGNORE INTO rejections SELECT id, ? FROM entries WHERE id=?''',
                       (digest(contract), entry_id))

    def record_reuse(self, identities):
        """Count only reuse that passed verification and was published."""
        with self.connection() as db:
            db.executemany('''UPDATE entries SET reuse_count=reuse_count+1,
                successes=successes+1,last_used=? WHERE id=?''',
                [(time.time(), identity) for identity in identities])

    def candidates(self, task, contracts, limit=15, *, unique_sources=False, eligible=None):
        if not 0 <= limit <= 15:
            raise ValueError('At most fifteen candidates supported')
        if not limit or (not self.path.exists() and not self.legacy.exists()):
            return []
        # Contracts have priority when bounding unusually long queries.
        terms = search_terms(' '.join(contracts.values()) + ' ' + task)[:128]
        if not terms:
            return []
        query = ' OR '.join('"' + word + '"' for word in terms)
        hashes = [digest(contract) for contract in contracts.values()]
        placeholders = ','.join('?' for _ in hashes) or 'NULL'
        with self.connection() as db:
            # Keep ranking and lazy source reads on the same database snapshot.
            db.execute('BEGIN')
            rows = db.execute(f'''SELECT e.seq FROM search JOIN entries e ON e.seq=search.rowid
                WHERE search MATCH ? AND e.entry_version=1 AND NOT EXISTS
                (SELECT 1 FROM rejections r WHERE r.entry_id=e.id AND r.contract_hash IN ({placeholders}))
                ORDER BY bm25(search),e.reuse_count DESC,e.successes DESC,e.last_used DESC,e.seq DESC
                LIMIT ?''', [query, *hashes, -1 if unique_sources or eligible else limit])
            candidates, seen = [], set()
            for row in ranked_entries(db, rows, limit):
                if unique_sources and row['source'] in seen:
                    continue
                entry = checked(row)
                if eligible is not None and not eligible(entry):
                    continue
                candidates.append(entry)
                seen.add(row['source'])
                if len(candidates) == limit:
                    break
            return candidates

    def prune(self, max_entries):
        """Explicit maintenance only; default admission never evicts learned entries.

        Retain current-version, frequently reused, repeatedly verified entries,
        breaking ties by recency. No claim of environment compatibility is made.
        """
        if not isinstance(max_entries, int) or max_entries < 0:
            raise ValueError('Nonnegative capacity required')
        with self.connection() as db:
            cursor = db.execute('''DELETE FROM entries WHERE seq IN (
                SELECT seq FROM entries ORDER BY (entry_version=1) DESC,
                reuse_count DESC,successes DESC,last_used DESC,seq DESC LIMIT -1 OFFSET ?)''',
                (max_entries,))
            return cursor.rowcount
