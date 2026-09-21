import { uniqueStrings } from './unique_repeat.mjs';
const input = ['a', 'B', 'a', 'b', 'A', '  x  ', '  x  ', 'a'];
const out = uniqueStrings(input);
console.log(JSON.stringify(out));
console.log('input unchanged:', JSON.stringify(input));
console.log('distinct count:', out.length);
console.log('case-sensitive:', out.includes('A') && out.includes('a') && out.includes('B') && out.includes('b'));
console.log('whitespace kept:', out.includes('  x  '));
