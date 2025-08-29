import { DetailedChanges } from './Detailedchanges';

export class BaseFileDiff {
    public changes: DetailedChanges;

    constructor(moduleName: string) {
        this.changes = new DetailedChanges(moduleName);
    }
}
