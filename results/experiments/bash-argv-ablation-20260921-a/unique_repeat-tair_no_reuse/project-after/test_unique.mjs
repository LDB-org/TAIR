import { uniqueStrings } from './unique_repeat.mjs';
const input = ['a', 'B', 'a', 'b', 'A', '  x  ', '  x  ', 'a'];
const out = uniqueStrings(input);
console.log(JSON.stringify(out));
console.log('input unchanged:', JSON.stringify(input));
console.log('case-sensitive:', out.includes('B') && out.includes('b') && out.includes('A'));
console.log('whitespace kept:', out.includes('  x  '));
console.log('order:', JSON.stringify(out) === JSON.stringify(['a','B','b','A','  x  ']));
