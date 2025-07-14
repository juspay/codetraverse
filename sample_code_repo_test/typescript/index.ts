/**
 * Entry point for the application.
 */

import defaultGreet, { greetUser as helloUser } from './utils'; // default + named + alias
import * as Utils from './utils';                               // namespace import
import { Admin, Person, DEFAULT_USER } from './models';         // named import
import type { Role, UserKeys, AliasOfUser } from './types';     // type-only import
import { func2 } from './models';


export function func1(): void {
    console.log('func1 start');
    func2();
    console.log('func1 end');
  }

export const APP_NAME = 'CodeTraverse';

export type AppNameType = typeof APP_NAME;                      // typeof operator

// namespace declaration & call
namespace AppNS {
  export const NS_VAL = 42;
  export function nsFunc(): number {
    return NS_VAL * 2;
  }
}

/**
 * Main function: logs greetings and exercises classes & generators.
 */
export async function main<T extends string>(username: T): Promise<void> {  // generic + constraint
  // type-only
  const userRole: Role = 'user';
  const user: AliasOfUser = {
    id: 1,
    name: username,
    role: userRole,
  };

  // function calls (default + alias)
  console.log(APP_NAME, defaultGreet(user));
  console.log(APP_NAME, helloUser(user));

  // instantiate classes, call methods, generate IDs
  const admin = new Admin(2, 'AdminUser', 'admin', 'extra');
  console.log('Admin says:', admin.greet());          // method + decorator
  for (const id of admin.generateIds()) {
    console.log('Generated ID:', id);
  }
  for await (const n of Utils.asyncGen()) {
    console.log('AsyncGen yields:', n);
  }

  console.log('Namespace call:', AppNS.nsFunc());
}
