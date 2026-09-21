import { uniqueStrings } from './unique_changed.mjs';
const input = ['Apple', 'banana', 'APPLE', 'Banana', 'cherry', '  Cherry  ', 'apple'];
const out = uniqueStrings(input);
console.log(JSON.stringify(out));
console.log('input unchanged:', JSON.stringify(input));
console.log('no mutation:', input.length === 7);
console.log('first occurrence order:', JSON.stringify(out) === JSON.stringify(['Apple','banana','cherry','  Cherry  ']));
console.log('whitespace preserved:', out.includes('  Cherry  '));
