import { Person } from './models.js';
import { greet_user } from './utils.js';
import * as utils from './utils.js';

function main() {
  const p = new Person("John", 30);
  greet_user(p);
  func_main();
}

function func_main() {
  console.log("func_main");
}

class Greeter {
  greet(name) {
    return `Hello, ${name}`;
  }
}

main();
