export class DetailedChanges {
    public moduleName: string;
    public changes: Record<string, any>;

    constructor(moduleName: string) {
        this.moduleName = moduleName;
        this.changes = {};
    }

    public add_change(category: string, change_type: string, item: any) {
        if (!this.changes[category]) {
            this.changes[category] = { added: [], deleted: [], modified: [] };
        }
        this.changes[category][change_type].push(item);
    }

    public to_dict() {
        return {
            moduleName: this.moduleName,
            changes: this.changes
        };
    }

    private capitalize(s: string): string {
        return s.charAt(0).toUpperCase() + s.slice(1);
    }
}
