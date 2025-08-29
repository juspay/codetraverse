import { runAstDiffFromConfig } from '../../codetraverse/utils/AstDifferOrchestrator';
import * as path from 'path';

import { Config } from '../../codetraverse/utils/AstDifferOrchestrator';

describe('AstDiffOrchestrator', () => {
    it('should run with a simple config', async () => {
        const config: Config = {
            provider_type: "local",
            local: {
                repo_path: path.join(__dirname, '..', '..')
            },
            from_commit: "HEAD~1",
            to_commit: "HEAD",
        };
        const result = await runAstDiffFromConfig(config);
        expect(result).toBeDefined();
    });
});
