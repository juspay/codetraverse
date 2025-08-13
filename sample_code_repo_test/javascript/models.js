import { Greeter } from './index.js';
import type_func from './types.js';

export class Person extends Greeter {
  constructor(name, age) {
    super();
    this.name = name;
    this.age = age;
  }

  greet() {
    return `Hello, my name is ${this.name}`;
  }

  set_name(name) {
    this.name = name;
  }
}

export function model_func() {
  type_func();
}
