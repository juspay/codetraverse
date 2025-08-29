import * as fs from 'fs';
import * as jsnx from 'jsnetworkx';
import { buildGraphFromSchema } from './utils/jsnetworkx_graph';

export function loadGraph(graphPath: string): jsnx.Graph | null {
    if (!fs.existsSync(graphPath)) {
        console.error(`Error: Graph file not found at ${graphPath}`);
        return null;
    }
    try {
        const data = JSON.parse(fs.readFileSync(graphPath, 'utf-8'));
        return buildGraphFromSchema(data);
    } catch (e) {
        if (e instanceof Error) {
            console.error(`Error reading or parsing graph file ${graphPath}: ${e.message}`);
        }
        return null;
    }
}
