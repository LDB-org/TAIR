import { uniqueStrings } from './unique_base.mjs';
const input = ['a', 'b', 'a', 'c', 'B', 'b', '  x  ', '  x  ', 'a'];
const out = uniqueStrings(input);
console.log(JSON.stringify(out));
console.log('input unchanged:', JSON.stringify(input));
console.log('case-sensitive:', JSON.stringify(uniqueStrings(['A','a','A'])));
console.log('no trim:', JSON.stringify(uniqueStrings([' x ','x',' x '])));
console.log('empty:', JSON.stringify(uniqueStrings([])));
