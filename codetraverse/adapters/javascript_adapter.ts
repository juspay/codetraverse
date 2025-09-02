import * as os from 'os';
import * as path from 'path';
import { Component } from '../types/types';

const JS_EXTS = new Set([".js", ".mjs", ".cjs", ".jsx"]);

// ---------- basic path helpers ----------
function norm(p: string): string {
    return p.replace(/\\/g, "/");
}

function ensureJsCandidate(pathNoExt: string): string {
    /** Append .js only if there isn't already a JS-like extension. */
    const ext = path.extname(pathNoExt);
    if (JS_EXTS.has(ext)) {
        return norm(pathNoExt);
    }
    return norm(pathNoExt + ".js");
}

function resolveRelative(fromModule: string, spec: string): string {
    /**
     * Resolve './x' '../y' against a repo-prefixed 'from_module' (like comp['module']).
     * Bare specs are returned as-is.
     */
    const baseDir = path.dirname(fromModule);
    const combined = path.normalize(path.join(baseDir, spec));
    return norm(combined);
}

function resolveSymbolInImports(
    callerModule: string,
    sym: string,
    importMap: { [key: string]: { [key: string]: [string, string] } },
    exportIndex: { [key: string]: { [key: string]: any } }
): string | null {
    /**
     * Map a local symbol (e.g., 'Greeter' or 'NS.Greeter') to a fully-qualified id:
     * - returns '<target_module>::<exported>' (named/default; default rewritten to declared name if known)
     * - returns '<target_module>::<prop>' for namespace imports (NS.Prop)
     * - falls back to same-module reference.
     */
    const imap = importMap[callerModule] || {};
    
    // Namespace import: NS.Greeter
    if (sym.includes(".")) {
        const dotIndex = sym.indexOf(".");
        const recv = sym.substring(0, dotIndex);
        const prop = sym.substring(dotIndex + 1);
        if (recv in imap) {
            const [tgtMod, exported] = imap[recv];
            // namespace import ('*') → use the property name as the symbol
            return `${tgtMod}::${prop}`;
        }
    }
    
    // Named/default import: Greeter
    if (sym in imap) {
        const [tgtMod, exported] = imap[sym];
        if (exported === "default") {
            const declared = (exportIndex[tgtMod] || {}).default;
            const toName = declared || "default";
            return `${tgtMod}::${toName}`;
        } else {
            return `${tgtMod}::${exported}`;
        }
    }
    
    // Relative (rare): './Greeter'
    if (sym.startsWith("./") || sym.startsWith("../")) {
        const tgtMod = ensureJsCandidate(resolveRelative(callerModule, sym));
        return `${tgtMod}::${path.basename(sym)}`;
    }
    
    // Fallback: same file
    return `${callerModule}::${sym}`;
}

// ---------- node id (simple & stable) ----------
function makeNodeId(comp: { [key: string]: any }): string | null {
    /**
     * - methods/ctors/fields: module::Class::method
     * - everything named: module::name
     * - literals are skipped as nodes
     */
    const kind = comp.kind;
    if (["number", "string", "template_string"].includes(kind)) {
        return null;
    }
    
    const module = comp.file_path || comp.module || process.env.CURRENT_FILE || "unknown";
    
    if (["method", "constructor", "field"].includes(kind) && comp.class && comp.name) {
        // Class.member form (keeps IDs consistent with your TS adaptor style)
        return `${module}::${comp.class}::${comp.name}`;
    }
    
    if (comp.name) {
        return `${module}::${comp.name}`;
    }
    
    if (comp.id) {
        return comp.id;
    }
    
    if (kind) {
        return `${module}::${kind}`;
    }
    
    return null;
}

// ---------- adaptor ----------
export function adaptJavascriptComponents(rawComponents: Component[]): { nodes: any[], edges: any[] } {
    /**
     * Input: list of components from the JS extractor.
     * Output: { "nodes": [...], "edges": [...] }.
     */
    const nodes: { [key: string]: any }[] = [];
    const edges: { [key: string]: any }[] = [];
    const existingNodes = new Set<string>();
    
    if (rawComponents.length > 0) {
        const first = rawComponents[0];
        process.env.ROOT_DIR = first.root_folder || process.env.ROOT_DIR || "";
        process.env.CURRENT_FILE = first.file_path || process.env.CURRENT_FILE || "";
    }
    
    // ---------- import map ----------
    // { module_path : { local_name : (resolved_target_module, exported_name|*|default) } }
    const importMap: { [key: string]: { [key: string]: [string, string] } } = {};
    
    for (const comp of rawComponents) {
        if (comp.kind !== "import") continue;
        
        const module = comp.module || comp.file_path;
        const stmt = comp.code || "";
        if (!module) continue;
        
        if (!(module in importMap)) {
            importMap[module] = {};
        }
        
        // named imports
        let m = stmt.match(/\s*import\s*{([^}]+)}\s*from\s*['"](.+?)['"]/);
        if (m) {
            const [, names, src] = m;
            const srcRel = src.startsWith(".") ? resolveRelative(module, src) : src;
            const srcPath = ensureJsCandidate(srcRel);
            for (const name of names.split(",").map(x => x.trim()).filter(x => x)) {
                if (name.includes(" as ")) {
                    const [orig, alias] = name.split(" as ").map(n => n.trim());
                    importMap[module][alias] = [srcPath, orig];
                } else {
                    importMap[module][name] = [srcPath, name];
                }
            }
            continue;
        }
        
        // default import
        m = stmt.match(/\s*import\s+([A-Za-z0-9_$]+)\s*from\s*['"](.+?)['"]/);
        if (m) {
            const [, local, src] = m;
            const srcRel = src.startsWith(".") ? resolveRelative(module, src) : src;
            const srcPath = ensureJsCandidate(srcRel);
            importMap[module][local] = [srcPath, "default"];
            continue;
        }
        
        // namespace import
        m = stmt.match(/\s*import\s+\*\s+as\s+([A-Za-z0-9_$]+)\s*from\s*['"](.+?)['"]/);
        if (m) {
            const [, ns, src] = m;
            const srcRel = src.startsWith(".") ? resolveRelative(module, src) : src;
            const srcPath = ensureJsCandidate(srcRel);
            importMap[module][ns] = [srcPath, "*"];
        }
    }
    
    // ---------- export index ----------
    // module_path -> {"default": <declared_name or None>, "named": set([...])}
    const exportIndex: { [key: string]: { [key: string]: any } } = {};
    
    for (const comp of rawComponents) {
        if (comp.kind !== "export") continue;
        
        const mod = comp.module || comp.file_path;
        if (!mod) continue;
        
        if (!(mod in exportIndex)) {
            exportIndex[mod] = { default: null, named: new Set() };
        }
        const info = exportIndex[mod];
        
        // named exports
        const name = comp.name;
        if (comp.default) {
            // prefer a real declared name if the extractor captured it (e.g., "type_func")
            if (name && name !== "default") {
                info.default = name;
            }
            // else leave as null (will fall back to "default")
        } else if (name) {
            info.named.add(name);
        }
    }
    
    // ---------- nodes ----------
    function addNode(comp: { [key: string]: any }) {
        const nodeId = makeNodeId(comp);
        if (!nodeId) return;
        
        const kind = comp.kind;
        
        // if the id already exists, prefer real declarations over export wrappers
        if (existingNodes.has(nodeId)) {
            const existing = nodes.find(n => n.id === nodeId);
            if (existing && existing.category === "export" && 
                ["function", "generator_function", "class", "method", "constructor"].includes(kind)) {
                // replace the export node with the declaration
                const index = nodes.findIndex(n => n.id === nodeId);
                if (index >= 0) {
                    nodes.splice(index, 1);
                }
                existingNodes.delete(nodeId);
            } else {
                return;
            }
        }
        
        const node: { [key: string]: any } = {
            id: nodeId,
            category: kind === "namespace" ? "namespace" : kind,
            parameters: comp.parameters,
            location: {
                start: comp.start_line,
                end: comp.end_line,
                module: comp.module,
            },
            bases: kind === "class" ? comp.bases : null,
        };
        
        // Remove null values
        Object.keys(node).forEach(key => {
            if (node[key] === null || node[key] === undefined) {
                delete node[key];
            }
        });
        
        nodes.push(node);
        existingNodes.add(nodeId);
    }
    
    for (const comp of rawComponents) {
        addNode(comp);
    }
    
    // ---------- helper: enclosing callable contexts ----------
    // function / generator_function / method / constructor / arrow_function contexts
    const contextsByModule: { [key: string]: [number, number, string][] } = {};
    
    for (const comp of rawComponents) {
        const kind = comp.kind;
        if (!["function", "generator_function", "method", "constructor", "arrow_function"].includes(kind)) {
            continue;
        }
        
        const nodeId = makeNodeId(comp);
        if (!nodeId) continue;
        
        const mod = comp.module || comp.file_path;
        const start = comp.start_line;
        const end = comp.end_line;
        if (!mod || start === null || start === undefined || end === null || end === undefined) {
            continue;
        }
        
        if (!(mod in contextsByModule)) {
            contextsByModule[mod] = [];
        }
        contextsByModule[mod].push([start, end, nodeId]);
    }
    
    function findEnclosingContext(mod: string, line: number): string | null {
        /** Pick the *smallest* span that contains the line. */
        let best: string | null = null;
        let bestSpan: number | null = null;
        
        for (const [s, e, nid] of contextsByModule[mod] || []) {
            if (s === null || s === undefined || e === null || e === undefined) continue;
            if (s <= line && line <= e) {
                const span = e - s;
                if (best === null || span < bestSpan!) {
                    best = nid;
                    bestSpan = span;
                }
            }
        }
        return best;
    }
    
    // ---------- class extends (resolved across files) ----------
    for (const comp of rawComponents) {
        if (comp.kind === "class" && comp.bases) {
            const frm = makeNodeId(comp);
            const callerModule = comp.module || comp.file_path;
            if (!frm || !callerModule) continue;
            
            for (let base of comp.bases) {
                base = (base || "").trim();
                if (!base) continue;
                
                // keep only Identifier(.Identifier)* (e.g., Greeter, NS.Greeter); drop generics or call tails
                const match = base.match(/^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*/);
                if (!match) continue;
                
                const baseSym = match[0];
                const toId = resolveSymbolInImports(callerModule, baseSym, importMap, exportIndex);
                if (toId && frm !== toId) {
                    edges.push({ from: frm, to: toId, relation: "extends" });
                }
            }
        }
    }
    
    // ---------- call edges (identifier/member) ----------
    function resolveCallTarget(
        callerModule: string,
        call: { [key: string]: any },
        importMapLocal: { [key: string]: { [key: string]: [string, string] } },
        exportIndexLocal: { [key: string]: { [key: string]: any } }
    ): string | null {
        const recv = call.receiver;
        const prop = call.property;
        const fn = call.function;
        const hint = call.resolved_hint || call.resolved_callee;
        const imap = importMapLocal[callerModule] || {};
        
        // Namespace: ns.foo()
        if (recv && recv in imap) {
            const [tgtMod, exported] = imap[recv];
            if (exported === "*") {
                return prop ? `${tgtMod}::${prop}` : null;
            }
            return `${tgtMod}::${prop || exported}`;
        }
        
        // Bare identifier imported: greet_user()
        if (fn && fn in imap) {
            const [tgtMod, exported] = imap[fn];
            if (exported === "default") {
                // prefer the declared default name if we know it
                const declared = (exportIndexLocal[tgtMod] || {}).default;
                return `${tgtMod}::${declared || 'default'}`;
            }
            return `${tgtMod}::${exported}`;
        }
        
        // Relative hint "./x::sym"
        if (hint && (hint.startsWith("./") || hint.startsWith("../"))) {
            const parts = hint.split("::");
            if (parts.length === 2) {
                const [relFile, sym] = parts;
                const absFile = resolveRelative(callerModule, relFile);
                return `${ensureJsCandidate(absFile)}::${sym}`;
            }
            return ensureJsCandidate(resolveRelative(callerModule, hint));
        }
        
        // Keep other hints (already absolute to a module) or unresolved
        return hint;
    }
    
    for (const comp of rawComponents) {
        const frm = makeNodeId(comp);
        if (!frm) continue;
        
        const callerModule = comp.module || comp.file_path;
        for (const call of comp.function_calls || []) {
            const tgt = resolveCallTarget(callerModule, call, importMap, exportIndex);
            if (tgt && frm !== tgt) {
                edges.push({ from: frm, to: tgt, relation: "calls" });
            }
        }
    }
    
    // ---------- NEW: instantiation edges from `new ...` ----------
    // Creates:
    // context_function → target_class (relation = "instantiates")
    // context_function → target_class.ctor (relation = "calls", if ctor node exists)
    for (const comp of rawComponents) {
        if (comp.kind !== "new_expression") continue;
        
        const callerModule = comp.module || comp.file_path;
        const line = comp.start_line;
        if (!callerModule || line === null || line === undefined) continue;
        
        const callerId = findEnclosingContext(callerModule, line);
        if (!callerId) continue; // skip top-level news for now
        
        let ctor = String(comp.constructor || "").trim();
        if (!ctor) continue;
        
        // Resolve constructor symbol to a module + class name
        let tgtModule: string | null = null;
        let clsName: string | null = null;
        const imap = importMap[callerModule] || {};
        
        if (ctor.includes(".")) {
            // e.g., NS.Person
            const dotIndex = ctor.indexOf(".");
            const recv = ctor.substring(0, dotIndex);
            const cls = ctor.substring(dotIndex + 1);
            clsName = cls;
            if (recv in imap) {
                const [tgtMod, exported] = imap[recv];
                tgtModule = tgtMod;
                // namespace import -> '*'
                // even if someone did "import * as NS from './x.js'", we just use clsName
                if (exported !== "*") {
                    // odd case, but fall back to exported if not namespace
                    clsName = clsName || exported;
                }
            }
        } else {
            // e.g., Person
            if (ctor in imap) {
                const [tgtMod, exported] = imap[ctor];
                tgtModule = tgtMod;
                if (exported === "default") {
                    const declared = (exportIndex[tgtModule] || {}).default;
                    clsName = declared || "default";
                } else {
                    clsName = exported;
                }
            } else {
                // local class in same module
                tgtModule = callerModule;
                clsName = ctor;
            }
        }
        
        if (!tgtModule || !clsName) continue;
        
        const classId = `${tgtModule}::${clsName}`;
        const ctorId = `${tgtModule}::${clsName}::constructor`;
        
        edges.push({ from: callerId, to: classId, relation: "instantiates" });
        if (nodes.some(n => n.id === ctorId)) {
            edges.push({ from: callerId, to: ctorId, relation: "calls" });
        }
    }
    
    // ---------- file deps (fdeps) ----------
    for (const comp of rawComponents) {
        if (comp.kind !== "import") continue;
        
        const mod = comp.module || comp.file_path;
        const stmt = comp.code || "";
        if (!mod || !stmt) continue;
        
        const match = stmt.match(/from\s*['"](.+?)['"]/);
        if (!match) continue;
        
        const src = match[1];
        let target: string;
        if (src.startsWith(".")) {
            target = ensureJsCandidate(resolveRelative(mod, src));
        } else {
            const vendorRoot = process.env.VENDOR_ROOT || "vendor";
            target = ensureJsCandidate(norm(path.join(vendorRoot, src)));
        }
        
        if (mod !== target) {
            edges.push({ from: mod, to: target, relation: "fdeps" });
        }
    }
    
    // ---------- class → member containment ----------
    for (const comp of rawComponents) {
        if (["method", "constructor", "field"].includes(comp.kind) && comp.class) {
            const classId = `${comp.module}::${comp.class}`;
            const memberId = makeNodeId(comp);
            if (classId && memberId && classId !== memberId) {
                // edges.push({ from: classId, to: memberId, relation: "member" });
                edges.push({ from: classId, to: memberId, relation: "calls" });
            }
        }
    }
    
    // keep only well-formed edges
    const filteredEdges = edges.filter(e => e.from && e.to);
    
    return { nodes: nodes, edges: filteredEdges };
}
