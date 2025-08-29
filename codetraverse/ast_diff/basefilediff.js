"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.BaseFileDiff = void 0;
var Detailedchanges_1 = require("./Detailedchanges");
var BaseFileDiff = /** @class */ (function () {
    function BaseFileDiff(moduleName) {
        this.changes = new Detailedchanges_1.DetailedChanges(moduleName);
    }
    return BaseFileDiff;
}());
exports.BaseFileDiff = BaseFileDiff;
