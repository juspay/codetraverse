import { User, getUserAlias as aliasGet } from './models';  // named + alias import

export class ChainClass {
    public finalMethod(): void {
      console.log('ChainClass.finalMethod invoked');
    }
  }

/** Greet a user by alias */
export function greetUser(user: User): string {
  const alias = aliasGet(user);                            // calls-edge
  return `Welcome, ${alias}!`;
}

// simple variable
export const greetingPrefix: string = 'Welcome';

/** Default export of a greeting function */
export default function defaultGreet(user: User): string {
  return `${greetingPrefix}, ${user.name}!`;
}

/** Arrow function example */
export const arrowFn = (x: number): number => x * 2;

/** Generator function declaration */
export function* genNumbers(): Generator<number> {
  yield 1;
  yield 2;
}

/** Async generator function */
export async function* asyncGen(): AsyncGenerator<number> {
  yield await Promise.resolve(3);
}
