import * as path from 'path';
import { Config } from './utils/AstDifferOrchestrator';

async function runTest() {
    const { runAstDiffFromConfig } = await import('./utils/AstDifferOrchestrator.js');
    const config: Config = {
        provider_type: "local",
        local: {
            repo_path: "/Users/pramod.p/euler-api-gateway"
        },
        from_commit: "HEAD~4",
        to_commit: "HEAD",
    };
    const result = await runAstDiffFromConfig(config);
    console.log(JSON.stringify(result, null, 2));
}

runTest();
