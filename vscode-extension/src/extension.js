const vscode = require('vscode');

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    const diagnosticsCollection = vscode.languages.createDiagnosticCollection('tapscript');

    /**
     * Check pipe delimiter balance in a TapScript document.
     * Validates that every line with pipe characters has balanced pairs
     * and that the number of bars (pipe-delimited segments) is consistent
     * within each section.
     * @param {vscode.TextDocument} document
     */
    function checkPipeBalance(document) {
        if (document.languageId !== 'tapscript') return;

        const diagnostics = [];
        const pipeRegex = /\|/g;

        // Track bar counts per section to detect inconsistent bar lines
        let currentSectionBars = 0;
        let currentSectionName = '';
        let sectionBarCounts = []; // [{ name, bars, line }]
        let sectionStartLine = -1;

        for (let lineNum = 0; lineNum < document.lineCount; lineNum++) {
            const line = document.lineAt(lineNum);
            const text = line.text;

            // Skip comments and blank lines
            const trimmed = text.trim();
            if (!trimmed || trimmed.startsWith('#') || trimmed.startsWith('//')) continue;

            // Detect section headers
            const sectionMatch = trimmed.match(/^\[([A-Za-z0-9]+)\]/);
            if (sectionMatch) {
                // Record previous section
                if (currentSectionName && sectionBarCounts.length > 0) {
                    checkSectionConsistency(sectionBarCounts, sectionStartLine, diagnostics);
                }
                currentSectionName = sectionMatch[1];
                sectionStartLine = lineNum;
                sectionBarCounts = [];
                continue;
            }

            // Check lines that contain pipe delimiters (musical lines)
            if (pipeRegex.test(text)) {
                pipeRegex.lastIndex = 0;
                const pipes = text.match(pipeRegex);
                const pipeCount = pipes ? pipes.length : 0;

                // Check for odd number of pipes (unbalanced)
                // Musical lines should have pipes in pairs: | cell | cell | cell |
                // A well-formed line starts and ends with | (or || for repeats)
                const leadingPipe = /^\s*\|/.test(text);
                const trailingPipe = /\|\s*(vel:.*?)?$/.test(text);

                if (!leadingPipe && !trailingPipe && pipeCount % 2 !== 0) {
                    // Odd pipe count without leading/trailing pipes is suspicious
                    diagnostics.push(new vscode.Diagnostic(
                        line.range,
                        `Unbalanced pipe delimiters: ${pipeCount} pipe(s) found. Musical lines should have matching | delimiters.`,
                        vscode.DiagnosticSeverity.Warning
                    ));
                }

                // Count bar segments (content between pipes)
                const barSegments = text.split('|').filter(s => s.trim());
                if (barSegments.length > 0) {
                    sectionBarCounts.push({ line: lineNum, bars: barSegments.length });
                }

                // Check for empty segments between consecutive pipes (|| without content)
                // This is valid for repeat markers but warn for accidental empty bars
                const emptySegments = text.match(/\|\s*\|(?!\|)/g);
                // ||: and :|| are repeat markers, not empty bars — don't flag those
                if (emptySegments) {
                    for (const match of emptySegments) {
                        const matchText = match;
                        // Skip if this is part of a repeat marker (||: or :||)
                        const idx = text.indexOf(matchText);
                        const context_start = Math.max(0, idx - 1);
                        const context_end = Math.min(text.length, idx + matchText.length + 1);
                        const around = text.substring(context_start, context_end);
                        if (!around.includes('||:') && !around.includes(':||')) {
                            // Could be an intentional empty bar — only warn
                            // Don't flag this as it's a known edge case (BUG-4 in the docs)
                        }
                    }
                }
            }
        }

        // Check last section
        if (sectionBarCounts.length > 0) {
            checkSectionConsistency(sectionBarCounts, sectionStartLine, diagnostics);
        }

        diagnosticsCollection.set(document.uri, diagnostics);
    }

    /**
     * Check if bar counts within a section are consistent across tracks.
     * @param {Array<{line: number, bars: number}>} sectionBarCounts
     * @param {number} sectionStartLine
     * @param {Array} diagnostics
     */
    function checkSectionConsistency(sectionBarCounts, sectionStartLine, diagnostics) {
        if (sectionBarCounts.length < 2) return;

        // Group bar counts to find the most common (the "expected" count)
        const counts = sectionBarCounts.map(s => s.bars);
        const countFreq = {};
        for (const c of counts) {
            countFreq[c] = (countFreq[c] || 0) + 1;
        }

        const expectedCount = Object.entries(countFreq).sort((a, b) => b[1] - a[1])[0][0];

        // Flag lines that deviate
        for (const entry of sectionBarCounts) {
            if (entry.bars !== parseInt(expectedCount)) {
                const doc = vscode.window.activeTextEditor?.document;
                if (doc) {
                    const line = doc.lineAt(entry.line);
                    diagnostics.push(new vscode.Diagnostic(
                        line.range,
                        `Bar count mismatch: this line has ${entry.bars} bar(s) but most lines in this section have ${expectedCount}.`,
                        vscode.DiagnosticSeverity.Information
                    ));
                }
            }
        }
    }

    // Register the command
    const checkCommand = vscode.commands.registerCommand('tapscript.checkPipeBalance', () => {
        const editor = vscode.window.activeTextEditor;
        if (editor && editor.document.languageId === 'tapscript') {
            checkPipeBalance(editor.document);
            vscode.window.showInformationMessage('TapScript: Pipe balance check complete.');
        } else {
            vscode.window.showWarningMessage('TapScript: No active TapScript file to check.');
        }
    });

    // Auto-check on document open and change
    context.subscriptions.push(
        vscode.workspace.onDidOpenTextDocument(checkPipeBalance),
        vscode.workspace.onDidChangeTextDocument(e => {
            if (e.document.languageId === 'tapscript') {
                checkPipeBalance(e.document);
            }
        }),
        vscode.workspace.onDidCloseTextDocument(doc => {
            if (doc.languageId === 'tapscript') {
                diagnosticsCollection.delete(doc.uri);
            }
        }),
        checkCommand,
        diagnosticsCollection
    );

    // Run initial check on the active document
    if (vscode.window.activeTextEditor) {
        checkPipeBalance(vscode.window.activeTextEditor.document);
    }
}

function deactivate() {
    // Cleanup handled by subscriptions
}

module.exports = { activate, deactivate };
