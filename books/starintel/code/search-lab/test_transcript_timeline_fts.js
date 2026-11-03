'use strict';
// Chapter 15: a search hit for an audio transcript does not recover utterances
// or establish a time-aligned transcript. Execute original pinned Server callbacks.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const PINS = Object.freeze({
  historical: '0ba24ba15b43f6895f4f6b53f6a7a860e3a5b66a',
  merged: 'dd6336f3047982db2f0e3615fed1413ed1e58e13',
});
const server = process.env.STAR_SEARCH_LAB_SERVER;
const historical = process.env.STAR_SEARCH_TRANSCRIPT_HISTORICAL_DESIGN ||
  (server && path.join(server, 'source/views/search.json'));
if (!historical) throw new Error('Pinned historical Server search.json is required');
const inputs = [['historical', historical]];
if (process.env.STAR_SEARCH_TRANSCRIPT_MERGED_DESIGN)
  inputs.push(['merged', process.env.STAR_SEARCH_TRANSCRIPT_MERGED_DESIGN]);

function sourceFor(generation, file) {
  const bytes = fs.readFileSync(file);
  const digest = crypto.createHash('sha1')
    .update(Buffer.from(`blob ${bytes.length}\0`)).update(bytes).digest('hex');
  assert.equal(digest, PINS[generation], `${generation}: index source pin mismatch`);
  const design = JSON.parse(bytes.toString('utf8'));
  assert.equal(design._id, '_design/search');
  assert.equal(design.indexes.fts.analyzer.fields.dataset, 'keyword');
  assert.equal(design.indexes.fts.analyzer.fields.tenant_id, 'keyword');
  return design.indexes.fts.index;
}

function capture(callback, document) {
  const emissions = [];
  const context = vm.createContext({index(field, value, options) {
    assert.equal(options.store, true);
    emissions.push([field, value]);
  }});
  context.callback = new vm.Script(`(${callback})`).runInContext(context, {timeout: 1000});
  context.document = structuredClone(document);
  new vm.Script('callback(document)').runInContext(context, {timeout: 1000});
  return emissions;
}
const values = (events, key) => events.filter(e => e[0] === key).map(e => e[1]);
const training = 'book-fictional-audio';
const ref = (type, name) => ({
  schema: `org.starintel/core@1/${type}`, id: `starintel:${type}:${name}`
});

// Fictional canonical-shaped examples informed by StarLang core@1 0.10.1.
// The test verifies raw index callbacks, NOT generated-SDK admission or storage.
const transcript = Object.freeze({
  id: 'starintel:transcript:clock-lab-01', rev: 'r1', dtype: 'transcript',
  dataset: training, schemaVersion: '0.10.1',
  title: 'Clock synchronization training audio',
  sourceMedia: ref('media', 'clock-lab-01'),
  text: 'The fictional signal occurs at thirty seconds.',
  segments: [ref('speech-segment', 'clock-lab-01')],
  wordTimings: [{word: 'thirty', startMs: 30000, endMs: 30500}],
  speakerTurns: [ref('speaker-turn', 'clock-lab-turn-01')],
});
const speech = Object.freeze({
  id: 'starintel:speechsegment:clock-lab-01', rev: 'r1', dtype: 'speech-segment',
  dataset: training, schemaVersion: '0.10.1',
  recording: ref('audio', 'clock-lab-01'),
  text: 'Thirty seconds after the synthetic start.',
  startMs: 30000, endMs: 32000, channel: 1,
  speaker: ref('speaker', 'clock-lab-demo'),
});
const audio = Object.freeze({
  id: 'starintel:audiosegment:clock-lab-01', rev: 'r1', dtype: 'audio-segment',
  dataset: training, schemaVersion: '0.10.1',
  recording: ref('audio', 'clock-lab-01'),
  startMs: 30000, endMs: 32000, channel: 1,
});
const nonIndexed = ['text', 'sourceMedia', 'segments', 'wordTimings',
  'speakerTurns', 'recording', 'startMs', 'endMs', 'speaker'];

for (const [generation, file] of inputs) {
  const callback = sourceFor(generation, file);
  const baseTranscript = capture(callback, transcript);
  const baseSpeech = capture(callback, speech);
  const baseAudio = capture(callback, audio);

  test(`${generation}: transcript label, dtype, and dataset are raw indexed fields`, () => {
    assert.deepEqual(values(baseTranscript, 'title'), [transcript.title]);
    assert.deepEqual(values(baseTranscript, 'dtype'), ['transcript']);
    assert.deepEqual(values(baseTranscript, 'dataset'), [training]);
    assert.deepEqual(values(baseTranscript, 'tenant_id'), ['default']);
  });
  test(`${generation}: changed spoken words and word timing leave raw emissions equal`, () => {
    const altered = {...transcript, text: 'An entirely different utterance.',
      wordTimings: [{word: 'different', startMs: 500, endMs: 1000}]};
    assert.deepEqual(capture(callback, altered), baseTranscript);
    assert.deepEqual(values(baseTranscript, 'text'), []);
    assert.deepEqual(values(baseTranscript, 'wordTimings'), []);
  });
  test(`${generation}: transcript source and speaker-turn changes do not appear`, () => {
    const altered = {...transcript, sourceMedia: ref('media', 'another-take'),
      speakerTurns: [], segments: []};
    assert.deepEqual(capture(callback, altered), baseTranscript);
    for (const key of ['sourceMedia', 'speakerTurns', 'segments'])
      assert.deepEqual(values(baseTranscript, key), []);
  });
  test(`${generation}: speechsegment utterance and timestamps remain unindexed`, () => {
    const altered = {...speech, text: 'Synthetic replacement speech',
      startMs: 1, endMs: 200, speaker: ref('speaker', 'different-demo')};
    assert.deepEqual(capture(callback, altered), baseSpeech);
    for (const key of ['text', 'startMs', 'endMs', 'speaker', 'recording'])
      assert.deepEqual(values(baseSpeech, key), []);
  });
  test(`${generation}: audiosegment timings are unindexed although channel is indexed`, () => {
    const altered = {...audio, startMs: 1000, endMs: 2000,
      recording: ref('audio', 'different-demo')};
    assert.deepEqual(capture(callback, altered), baseAudio);
    assert.deepEqual(values(baseAudio, 'channel'), [1]);
    for (const key of ['startMs', 'endMs', 'recording'])
      assert.deepEqual(values(baseAudio, key), []);
  });
  test(`${generation}: raw channel hit is not a transcript utterance`, () => {
    assert.deepEqual(values(baseSpeech, 'channel'), [1]);
    const changed = capture(callback, {...speech, channel: 2});
    assert.notDeepEqual(changed, baseSpeech);
    assert.deepEqual(values(changed, 'channel'), [2]);
    assert.deepEqual(values(changed, 'text'), []);
  });
  test(`${generation}: title update is an actual positive-control index change`, () => {
    const changed = capture(callback, {...transcript, title: 'Different training audio'});
    assert.notDeepEqual(changed, baseTranscript);
    assert.deepEqual(values(changed, 'title'), ['Different training audio']);
  });
  test(`${generation}: dataset is emitted but the callback does not authorize it`, () => {
    const changed = capture(callback, {...transcript, dataset: 'book-restricted-audio'});
    assert.notDeepEqual(changed, baseTranscript);
    assert.deepEqual(values(changed, 'dataset'), ['book-restricted-audio']);
    for (const key of nonIndexed) assert.deepEqual(values(changed, key), []);
  });
  test(`${generation}: nested data speech text still is not indexed`, () => {
    const changed = capture(callback, {...speech,
      data: {text: 'Another fictional sentence', startMs: 1, endMs: 2}});
    assert.deepEqual(changed, baseSpeech);
  });
  test(`${generation}: text-indexing mutant demonstrates the missing raw field`, () => {
    const needle = "add('title',doc.title);";
    assert.equal(callback.split(needle).length, 2, 'mutation anchor drift');
    const mutant = callback.replace(needle, needle + "add('text',doc.text);");
    const changed = capture(mutant, transcript);
    assert.deepEqual(values(changed, 'text'), [transcript.text]);
    assert.notDeepEqual(changed, baseTranscript);
    if (process.env.STAR_SEARCH_TRANSCRIPT_RED === '1')
      assert.deepEqual(changed, baseTranscript,
        'intentional RED: mutant emitted canonical transcript text');
  });
}
