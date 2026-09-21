import { uniqueStrings } from './unique_base.mjs';
const input = ['a', 'b', 'a', 'c', 'b', 'A'];
const out = uniqueStrings(input);
console.log(JSON.stringify(out));
console.log('input unchanged:', JSON.stringify(input));
console.log('distinct count:', out.length);
console.log('case-sensitive:', out.includes('A') && out.includes('a'));
const withSpace = [' x ', 'x', ' x '];
console.log('no trim:', JSON.stringify(uniqueStrings(withSpace)));
