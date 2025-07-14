/**
 * A simple method decorator that logs calls.
 */
export function log(target: any, propertyKey: string | symbol): any {
    return function (descriptor: PropertyDescriptor) {
      const original = descriptor.value;
      descriptor.value = function (...args: any[]) {
        console.log(`Calling ${String(propertyKey)}`);
        return original.apply(this, args);
      };
      return descriptor;
    };
  }
  
  import type { Role } from './types';            // type-only import
  import { func3 } from './types';
  
  export function func2(): void {
    console.log('func2 start');
    func3();
    console.log('func2 end');
  }
  
  // index signature
  export interface User {
    id: number;
    name: string;
    role: Role;
    [key: string]: any;                            // index_signature
  }
  
  // interface extends
  export interface Timestamped {
    createdAt: Date;
  }
  export interface BaseUser extends Timestamped {
    id: number;
    name: string;
  }
  
  export class Person {
    public id: number;
    public name: string;
    private _role: Role = 'user';
    static instanceCount: number = 0;               // static field
    readonly createdAt: Date;                       // readonly field
  
    constructor(id: number, name: string, role: Role) {
      this.id = id;
      this.name = name;
      this._role = role;
      this.createdAt = new Date();
      Person.instanceCount++;
    }
  
    @log                                            // decorator
    greet(): string {                               // method
      return `Hello, ${this.name}`;
    }
  
    get role(): Role {                              // getter
      return this._role;
    }
  
    set role(r: Role) {                             // setter
      this._role = r;
    }
  
    *generateIds(): Generator<number> {             // generator method
      yield this.id;
    }
  }
  
  export class Admin extends Person implements BaseUser { // extends + implements
    extra: string;
  
    constructor(id: number, name: string, role: Role, extra: string) {
      super(id, name, role);
      this.extra = extra;
    }
  
    promote(): void {
      this.role = 'admin';
    }
  
    override greet(): string {                      // override
      return `Admin ${this.name} greets you!`;
    }
  }
  
  // simple variable
  export const DEFAULT_USER: User = {
    id: 0,
    name: 'Guest',
    role: 'user'
  };
  
  /**
   * A small utility that your utils.ts can import.
   */
  export function getUserAlias(user: User): string {
    return `${user.name}#${user.id}`;
  }
  
  // helper namespace with an exported function
  export namespace helper {
    export function logSomething(msg: string): void {
      console.log('[helper] ' + msg);
    }
  }
  