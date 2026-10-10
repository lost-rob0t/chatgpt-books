// Execute the maintained index function. This captures emissions, not Lucene.
'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const design = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const emissions = [];
const context = vm.createContext({index: (field, value, options) => {
  emissions.push({field, value, options});
}});
// The runner checks an immutable, clean source pin before executing this code.
const indexer = new vm.Script('(' + design.indexes.fts.index + ')').runInContext(context);
context.document = input;
context.indexer = indexer;
new vm.Script('indexer(document)').runInContext(context, {timeout: 1000});
process.stdout.write(JSON.stringify(emissions));
