import assert from 'node:assert/strict';
import test from 'node:test';
import {answerLetter, shuffleQuestion} from '../app/static/quiz.mjs';

for (let correctIndex = 0; correctIndex < 4; correctIndex++) {
  test(`Preserves answer ID and text across all 24 permutations, source index ${correctIndex}`, () => {
    const question = Object.freeze({
      question: 'Which entry is correct?',
      options: Object.freeze(['Same label', 'Different', 'Same label', 'Last']),
      correct_index: correctIndex
    });
    const permutations = new Set();
    const positions = new Set();
    for (let fourth = 0; fourth < 4; fourth++) {
      for (let third = 0; third < 3; third++) {
        for (let second = 0; second < 2; second++) {
          const draws = [(fourth + .1) / 4, (third + .1) / 3, (second + .1) / 2];
          const result = shuffleQuestion(question, () => draws.shift());
          permutations.add(result.options.map(option => option.id).join());
          positions.add(result.correctIndex);
          assert.equal(result.correctId, correctIndex);
          assert.equal(result.options[result.correctIndex].id, correctIndex);
          assert.equal(result.correctLetter, answerLetter(result.correctIndex));
          for (const option of result.options) assert.equal(option.text, question.options[option.id]);
        }
      }
    }
    assert.equal(permutations.size, 24);
    assert.deepEqual([...positions].sort(), [0, 1, 2, 3]);
  });
}

test('Rejects invalid answer indices', () => {
  assert.throws(() => shuffleQuestion({options: ['a', 'b'], correct_index: 2}), RangeError);
});

