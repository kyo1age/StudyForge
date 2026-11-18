/**
 * IDs come from source positions and survive every permutation, even for identical
 * option labels. The saved question and its text remain unchanged.
 */
export function shuffleQuestion(question, random = Math.random) {
  const options = question.options.map((text, id) => ({id, text}));
  if (!Number.isInteger(question.correct_index) || !options[question.correct_index]) {
    throw new RangeError('Invalid correct answer index');
  }
  const correctId = options[question.correct_index].id;
  for (let last = options.length - 1; last > 0; last--) {
    const index = Math.floor(random() * (last + 1));
    [options[last], options[index]] = [options[index], options[last]];
  }
  const correctIndex = options.findIndex(option => option.id === correctId);
  return {
    question: question.question, options, correctId, correctIndex,
    correctLetter: answerLetter(correctIndex)
  };
}

export const answerLetter = index => String.fromCharCode(65 + index);

