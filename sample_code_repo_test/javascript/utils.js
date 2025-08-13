import { Person } from './models.js';
import { model_func } from './models.js';

export function greet_user(p) {
  p.greet();
  print_person(p);
}

function print_person(p) {
  console.log(p);
}

export function util_func() {
  model_func();
}

// New function for feature coverage
export function feature_coverage_func() {
  // variable_declaration (var)
  var x = 10;

  // lexical_declaration (let)
  let y = 20;

  // arrow_function
  const add = (a, b) => a + b;
  add(x, y);

  // if_statement
  if (x > 5) {
    console.log("x is greater than 5");
  }

  // for_statement with continue and break
  let sum = 0;
  myLabel:
  for (let i = 0; i < 5; i++) {
    if (i === 1) {
      continue; // continue_statement
    }
    if (i === 4) {
      break myLabel; // break_statement with label
    }
    sum += i; // augmented_assignment_expression
  }

  // while_statement
  let j = 0;
  while (j < 2) {
    console.log("while loop");
    j++;
  }

  // do_statement
  let k = 0;
  do {
    console.log("do-while loop");
    k++;
  } while (k < 2);

  // switch_statement
  const expr = 'Papayas';
  switch (expr) {
    case 'Oranges':
      console.log('Oranges are $0.59 a pound.');
      break;
    case 'Papayas':
      console.log('Papayas are $2.79 a pound.');
      break;
    default:
      console.log(`Sorry, we are out of ${expr}.`);
  }

  // try_statement, throw_statement
  try {
    throw new Error("This is an error");
  } catch (e) {
    console.error(e.message);
  }

  // debugger_statement
  debugger;

  // empty_statement
  ;

  // labeled_statement is already used with the for loop

  // generator_function_declaration
  function* idMaker() {
    var index = 0;
    while (true)
      yield index++; // yield_expression
  }
  var gen = idMaker();
  console.log(gen.next().value);

  // array
  const arr = [1, 2, 3];
  console.log(arr[0]); // subscript_expression

  // object
  const person_obj = { name: "John", age: 30 };

  // function_expression
  const multiply = function(a, b) { return a * b; };
  multiply(2, 3);

  // class_expression
  const MyClass = class {
    constructor() {}
    myMethod() { return 'Hello'; }
  };
  new MyClass();

  // ternary_expression
  const status = y > 10 ? 'big' : 'small';
  console.log(status);
  
  // sequence_expression
  let z;
  z = (x++, y++);
  
  // parenthesized_expression
  const paren = (2 + 3);
  
  // async/await
  async function asyncFunc() {
    return Promise.resolve(1);
  }
  async function mainAsync() {
    const result = await asyncFunc(); // await_expression
    console.log(result);
  }
  mainAsync();

  // with_statement
  const with_obj = { prop: "hello" };
  with (with_obj) {
    console.log(prop);
  }

  // generator_function (as expression)
  const gen_expr = function*() {
    yield 1;
  };
  gen_expr();

  // member_expression (as standalone expression)
  person_obj.age;
}

// Top-level expressions
"this is a string expression";
12345;
`this is a template string expression`;
