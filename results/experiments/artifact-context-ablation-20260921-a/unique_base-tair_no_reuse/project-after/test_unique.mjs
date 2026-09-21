import { uniqueStrings } from './unique_base.mjs';
const input = ['a', 'b', 'a', 'c', 'b', 'A', '  a  ', 'a'];
const out = uniqueStrings(input);
console.log(JSON.stringify(out));
console.log('input unchanged:', JSON.stringify(input));
console.log('case-sensitive:', out.includes('A') && out.includes('a'));
console.log('whitespace kept:', out.includes('  a  '));
console.log('order:', JSON.stringify(out) === JSON.stringify(['a','b','c','A','  a  ']));
