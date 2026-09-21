import { uniqueStrings } from './unique_repeat.mjs';
const input = ['a', 'b', 'a', 'c', 'b', 'A', '  x  ', '  x  ', 'a'];
const out = uniqueStrings(input);
console.log(JSON.stringify(out));
console.log('input unchanged:', JSON.stringify(input));
console.log('case-sensitive:', JSON.stringify(uniqueStrings(['a','A','a'])));
console.log('whitespace kept:', JSON.stringify(uniqueStrings([' x ',' x ','x'])));
console.log('empty:', JSON.stringify(uniqueStrings([])));
