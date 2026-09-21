import { uniqueStrings } from './unique_base.mjs';
const input = ['a', 'b', 'a', 'c', 'b', 'A', '  x  ', '  x  ', ''];
const out = uniqueStrings(input);
console.log(JSON.stringify(out));
console.log('input unchanged:', JSON.stringify(input));
console.log('case-sensitive:', out.includes('A') && out.indexOf('a') !== out.indexOf('A'));
console.log('no trim:', out.includes('  x  '));
console.log('empty preserved:', out.includes(''));
