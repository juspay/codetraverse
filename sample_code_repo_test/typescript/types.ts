import { User, DEFAULT_USER } from './models';
import { ChainClass } from './utils';


export function func3(): void {
    console.log('func3 start');
    const c = new ChainClass();
    c.finalMethod();
    console.log('func3 end');
  }


/** Union of string literals → literal_type nodes */
export type Role = 'admin' | 'user';

/** keyof operator → keyof node */
export type UserKeys = keyof User;

/** Simple re-aliasing → type_dependency edge */
export type AliasOfUser = User;

/** typeof on a value → typeof node */
export type DefaultUserType = typeof DEFAULT_USER;

/** Generic with constraint → type_parameters + constraints */
export type Box<T extends string | number> = {
  value: T;
};

/** Union type → intersection/union handling */
export type Nullable<T> = T | null;

/** Utility types to exercise UTILITY_TYPES set */
export type UserRecord = Record<string, User>;
export type PartialUser = Partial<User>;

/** Mapped type → index_signature + mapped_type_clause */
export type MappedUser = {
  [P in keyof User]: User[P];
};

/** Conditional type → conditional_type handling */
export type ConditionalNever<T> = T extends 'a' ? 'yes' : 'no';

/** Enum declaration → enum nodes */
export enum Status {
  Active = 'active',
  Inactive = 'inactive',
  Pending = 'pending'
}
