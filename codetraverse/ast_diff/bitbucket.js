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
exports.BitBucket = void 0;
var axios_1 = require("axios");
function handleResponse(response, processor) {
    return __awaiter(this, void 0, void 0, function () {
        return __generator(this, function (_a) {
            if (response.status === 200) {
                try {
                    return [2 /*return*/, processor(response)];
                }
                catch (e) {
                    console.error("Error: Failed to parse JSON response.");
                    return [2 /*return*/, null];
                }
            }
            console.error("Error: Received status code ".concat(response.status));
            console.error(response.data);
            return [2 /*return*/, null];
        });
    });
}
var BitBucket = /** @class */ (function () {
    function BitBucket(options) {
        this.baseUrl = options.base_url;
        this.projectKey = options.project_key;
        this.repoSlug = options.repo_slug;
        this.auth = options.auth;
        this.headers = options.headers || { 'Accept': 'application/json' };
        this.FILE_CONTENT_URL = "".concat(this.baseUrl, "/api/latest/projects/").concat(this.projectKey, "/repos/").concat(this.repoSlug, "/browse/{path}");
        this.GET_PR_URL = "".concat(this.baseUrl, "/api/latest/projects/").concat(this.projectKey, "/repos/").concat(this.repoSlug, "/pull-requests/{pullRequestId}");
        this.GET_LATEST_COMMIT_URL = "".concat(this.baseUrl, "/api/latest/projects/").concat(this.projectKey, "/repos/").concat(this.repoSlug, "/commits/{branchName}?limit=1");
        this.DIFF_URL = "".concat(this.baseUrl, "/api/latest/projects/").concat(this.projectKey, "/repos/").concat(this.repoSlug, "/compare/diff");
        this.DIFF_URL_RAW = "".concat(this.baseUrl, "/api/latest/projects/").concat(this.projectKey, "/repos/").concat(this.repoSlug, "/diff");
        this.GET_PRS_URL = "".concat(this.baseUrl, "/api/latest/projects/").concat(this.projectKey, "/repos/").concat(this.repoSlug, "/pull-requests?state=OPEN&at=refs/heads/{sourceBranch}&direction=OUTGOING");
    }
    BitBucket.prototype.getFilePathFromObject = function (json_object) {
        if (json_object.parent === "") {
            return json_object.name;
        }
        return "".concat(json_object.parent, "/").concat(json_object.name);
    };
    BitBucket.prototype.getChangedFilesFromCommits = function (fromCommit, toCommit) {
        return __awaiter(this, void 0, void 0, function () {
            var discoverFiles, finalUrl, params, config, response;
            var _this = this;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        discoverFiles = function (response) {
                            var jsonData = response.data;
                            var changes = { added: [], deleted: [], modified: [] };
                            for (var _i = 0, _a = jsonData.diffs || []; _i < _a.length; _i++) {
                                var diff = _a[_i];
                                if (!diff.source) {
                                    changes.added.push(_this.getFilePathFromObject(diff.destination));
                                }
                                else if (!diff.destination) {
                                    changes.deleted.push(_this.getFilePathFromObject(diff.source));
                                }
                                else {
                                    changes.modified.push(_this.getFilePathFromObject(diff.source));
                                }
                            }
                            return changes;
                        };
                        finalUrl = this.DIFF_URL.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug);
                        params = { to: toCommit, from: fromCommit };
                        config = { auth: this.auth, headers: this.headers, params: params };
                        return [4 /*yield*/, axios_1.default.get(finalUrl, config)];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, handleResponse(response, discoverFiles)];
                }
            });
        });
    };
    BitBucket.prototype.getChangedFilesFromCommitsRaw = function (fromCommit, toCommit) {
        return __awaiter(this, void 0, void 0, function () {
            var finalUrl, params, config, response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        finalUrl = this.DIFF_URL_RAW.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug);
                        params = { to: toCommit, from: fromCommit };
                        config = { auth: this.auth, headers: this.headers, params: params };
                        return [4 /*yield*/, axios_1.default.get(finalUrl, config)];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, handleResponse(response, function (res) { return res.data; })];
                }
            });
        });
    };
    BitBucket.prototype.getPrBitbucket = function (prId) {
        return __awaiter(this, void 0, void 0, function () {
            var finalUrl, config, response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        finalUrl = this.GET_PR_URL.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug).replace('{pullRequestId}', prId);
                        config = { auth: this.auth, headers: this.headers };
                        return [4 /*yield*/, axios_1.default.get(finalUrl, config)];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, handleResponse(response, function (res) { return res.data; })];
                }
            });
        });
    };
    BitBucket.prototype.getLatestCommitFromBranch = function (branchName) {
        return __awaiter(this, void 0, void 0, function () {
            var handleCommitResponse, finalUrl, config, response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        handleCommitResponse = function (response) { return response.data.id; };
                        finalUrl = this.GET_LATEST_COMMIT_URL.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug).replace('{branchName}', branchName);
                        config = { auth: this.auth, headers: this.headers };
                        return [4 /*yield*/, axios_1.default.get(finalUrl, config)];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, handleResponse(response, handleCommitResponse)];
                }
            });
        });
    };
    BitBucket.prototype.getPrId = function (branchName) {
        return __awaiter(this, void 0, void 0, function () {
            var handlePrResponse, finalUrl, config, response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        handlePrResponse = function (response) {
                            var formattedResponse = response.data;
                            for (var _i = 0, _a = formattedResponse.values || []; _i < _a.length; _i++) {
                                var pr = _a[_i];
                                if (pr.fromRef.displayId === branchName) {
                                    return [pr.id, pr.fromRef.latestCommit, pr.toRef.latestCommit];
                                }
                            }
                            return null;
                        };
                        finalUrl = this.GET_PRS_URL.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug).replace('{sourceBranch}', branchName);
                        config = { auth: this.auth, headers: this.headers };
                        return [4 /*yield*/, axios_1.default.get(finalUrl, config)];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, handleResponse(response, handlePrResponse)];
                }
            });
        });
    };
    BitBucket.prototype.getFileContent = function (filePath_1) {
        return __awaiter(this, arguments, void 0, function (filePath, commit) {
            var handleFileResponse, finalUrl, params, config, response;
            if (commit === void 0) { commit = ""; }
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        handleFileResponse = function (response) {
                            var formattedResponse = response.data;
                            return (formattedResponse.lines || []).map(function (line) { return line.text; }).join('\n');
                        };
                        finalUrl = this.FILE_CONTENT_URL.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug).replace('{path}', filePath);
                        params = { at: commit, limit: 10000 };
                        config = { auth: this.auth, headers: this.headers, params: params };
                        return [4 /*yield*/, axios_1.default.get(finalUrl, config)];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, handleResponse(response, handleFileResponse)];
                }
            });
        });
    };
    return BitBucket;
}());
exports.BitBucket = BitBucket;
