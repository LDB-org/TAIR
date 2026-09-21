import { uniqueStrings } from './unique_repeat.mjs';
const input = ['a', 'b', 'A', 'a', 'c', 'b', '  x  ', '  x  ', 'x'];
const out = uniqueStrings(input);
console.log(JSON.stringify(out));
console.log('input unchanged:', JSON.stringify(input));
console.log('distinct count:', out.length);
console.log('case-sensitive:', out.includes('A') && out.includes('a'));
console.log('whitespace kept:', out.includes('  x  '));
