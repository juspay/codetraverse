"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __generator = (this && this.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
    return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (g && (g = 0, op[0] && (_ = 0)), _) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.GitWrapper = void 0;
var fs = require("fs");
var simple_git_1 = require("simple-git");
var unidiff_1 = require("unidiff");
var GitWrapper = /** @class */ (function () {
    function GitWrapper(repoPath) {
        this.repoPath = repoPath;
        if (!fs.existsSync(repoPath)) {
            throw new Error("Repository path does not exist: ".concat(repoPath));
        }
        this.git = (0, simple_git_1.default)(repoPath);
    }
    GitWrapper.prototype.getLatestCommitFromBranch = function (branchName) {
        return __awaiter(this, void 0, void 0, function () {
            var e_1, fullRef, log, e_2, log;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        _a.trys.push([0, 2, , 3]);
                        return [4 /*yield*/, this.git.fetch("origin", branchName)];
                    case 1:
                        _a.sent();
                        return [3 /*break*/, 3];
                    case 2:
                        e_1 = _a.sent();
                        console.warn("Warning: Failed to fetch branch '".concat(branchName, "': ").concat(e_1.message));
                        return [3 /*break*/, 3];
                    case 3:
                        fullRef = "origin/".concat(branchName);
                        _a.label = 4;
                    case 4:
                        _a.trys.push([4, 6, , 8]);
                        return [4 /*yield*/, this.git.log([fullRef, '-n', '1'])];
                    case 5:
                        log = _a.sent();
                        return [2 /*return*/, log.latest.hash];
                    case 6:
                        e_2 = _a.sent();
                        return [4 /*yield*/, this.git.log([branchName, '-n', '1'])];
                    case 7:
                        log = _a.sent();
                        return [2 /*return*/, log.latest.hash];
                    case 8: return [2 /*return*/];
                }
            });
        });
    };
    GitWrapper.prototype.getCommonAncestor = function (branch1, branch2) {
        return __awaiter(this, void 0, void 0, function () {
            var e_3, ref1, ref2, mergeBase;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        _a.trys.push([0, 3, , 4]);
                        return [4 /*yield*/, this.git.fetch("origin", branch1)];
                    case 1:
                        _a.sent();
                        return [4 /*yield*/, this.git.fetch("origin", branch2)];
                    case 2:
                        _a.sent();
                        return [3 /*break*/, 4];
                    case 3:
                        e_3 = _a.sent();
                        console.warn("Warning: fetch failed: ".concat(e_3.message));
                        return [3 /*break*/, 4];
                    case 4:
                        ref1 = "origin/".concat(branch1);
                        ref2 = "origin/".concat(branch2);
                        return [4 /*yield*/, this.git.raw('merge-base', ref1, ref2)];
                    case 5:
                        mergeBase = _a.sent();
                        return [2 /*return*/, mergeBase.trim()];
                }
            });
        });
    };
    GitWrapper.prototype.getChangedFilesFromCommits = function (toCommit, fromCommit) {
        return __awaiter(this, void 0, void 0, function () {
            var diff, changes;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0: return [4 /*yield*/, this.git.diffSummary([fromCommit, toCommit])];
                    case 1:
                        diff = _a.sent();
                        changes = {
                            added: diff.files.filter(function (f) { return f.binary === false && f.changes === f.insertions && f.deletions === 0; }).map(function (f) { return f.file; }),
                            deleted: diff.files.filter(function (f) { return f.binary === false && f.changes === f.deletions && f.insertions === 0; }).map(function (f) { return f.file; }),
                            modified: diff.files.filter(function (f) { return f.binary === false && f.insertions > 0 && f.deletions > 0; }).map(function (f) { return f.file; }),
                        };
                        return [2 /*return*/, changes];
                }
            });
        });
    };
    GitWrapper.prototype.getChangedFilesFromCommitsRaw = function (fromCommit, toCommit) {
        return __awaiter(this, void 0, void 0, function () {
            return __generator(this, function (_a) {
                return [2 /*return*/, this.git.diff([fromCommit, toCommit])];
            });
        });
    };
    GitWrapper.prototype.getStructuredDiff = function (fromCommit, toCommit) {
        return __awaiter(this, void 0, void 0, function () {
            var addedChanges, removedChanges, rawDiff, patch, _i, patch_1, patchedFile, filename, _a, _b, hunk, _c, _d, line;
            return __generator(this, function (_e) {
                switch (_e.label) {
                    case 0:
                        addedChanges = {};
                        removedChanges = {};
                        return [4 /*yield*/, this.git.diff(["".concat(fromCommit, "..").concat(toCommit), '-U0'])];
                    case 1:
                        rawDiff = _e.sent();
                        patch = (0, unidiff_1.parse)(rawDiff);
                        for (_i = 0, patch_1 = patch; _i < patch_1.length; _i++) {
                            patchedFile = patch_1[_i];
                            filename = patchedFile.to.split('/').pop();
                            for (_a = 0, _b = patchedFile.hunks; _a < _b.length; _a++) {
                                hunk = _b[_a];
                                for (_c = 0, _d = hunk.lines; _c < _d.length; _c++) {
                                    line = _d[_c];
                                    if (line.type === 'add') {
                                        if (!addedChanges[filename]) {
                                            addedChanges[filename] = [];
                                        }
                                        addedChanges[filename].push([line.ln, line.text]);
                                    }
                                    else if (line.type === 'del') {
                                        if (!removedChanges[filename]) {
                                            removedChanges[filename] = [];
                                        }
                                        removedChanges[filename].push([line.ln, line.text]);
                                    }
                                }
                            }
                        }
                        return [2 /*return*/, { added: addedChanges, removed: removedChanges }];
                }
            });
        });
    };
    GitWrapper.prototype.getFileContent = function (filePath_1) {
        return __awaiter(this, arguments, void 0, function (filePath, commit) {
            var e_4;
            if (commit === void 0) { commit = "HEAD"; }
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        _a.trys.push([0, 2, , 3]);
                        return [4 /*yield*/, this.git.show("".concat(commit, ":").concat(filePath))];
                    case 1: return [2 /*return*/, _a.sent()];
                    case 2:
                        e_4 = _a.sent();
                        throw new Error("File '".concat(filePath, "' not found at commit '").concat(commit, "'. Error: ").concat(e_4.message));
                    case 3: return [2 /*return*/];
                }
            });
        });
    };
    return GitWrapper;
}());
exports.GitWrapper = GitWrapper;
