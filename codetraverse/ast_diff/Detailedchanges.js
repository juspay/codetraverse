"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DetailedChanges = void 0;
var DetailedChanges = /** @class */ (function () {
    function DetailedChanges(moduleName) {
        this.moduleName = moduleName;
        this.changes = {};
    }
    DetailedChanges.prototype.add_change = function (category, change_type, item) {
        if (!this.changes[category]) {
            this.changes[category] = { added: [], deleted: [], modified: [] };
        }
        this.changes[category][change_type].push(item);
    };
    DetailedChanges.prototype.to_dict = function () {
        var result = { moduleName: this.moduleName };
        for (var category in this.changes) {
            var categoryChanges = this.changes[category];
            if (categoryChanges.added.length > 0) {
                result["added".concat(this.capitalize(category))] = categoryChanges.added;
            }
            if (categoryChanges.deleted.length > 0) {
                result["deleted".concat(this.capitalize(category))] = categoryChanges.deleted;
            }
            if (categoryChanges.modified.length > 0) {
                result["modified".concat(this.capitalize(category))] = categoryChanges.modified;
            }
        }
        return result;
    };
    DetailedChanges.prototype.capitalize = function (s) {
        return s.charAt(0).toUpperCase() + s.slice(1);
    };
    return DetailedChanges;
}());
exports.DetailedChanges = DetailedChanges;
