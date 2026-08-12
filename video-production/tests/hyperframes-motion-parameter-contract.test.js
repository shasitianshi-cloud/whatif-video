'use strict';

const assert = require('assert');
const { normalizeMotion } = require('../src/build-hyperframes-composition.js');

function expectInvalid(motion) {
  assert.throws(() => normalizeMotion(motion), err => err && err.message === 'INVALID_MOTION_PARAMETERS');
}

const nested = normalizeMotion({
  parameters: {
    from: { x_percent: -2, y_percent: 0, scale: 1.04 },
    to: { x_percent: 2, y_percent: 1, scale: 1.0 },
  },
});
assert.deepStrictEqual(nested, {
  from: { x_percent: -2, y_percent: 0, scale: 1.04 },
  to: { x_percent: 2, y_percent: 1, scale: 1.0 },
});

const legacyExplicit = normalizeMotion({
  parameters: {
    start_x_percent: 0,
    start_y_percent: 0,
    start_scale: 1,
    end_x_percent: 3,
    end_y_percent: -1,
    end_scale: 1.05,
  },
});
assert.deepStrictEqual(legacyExplicit, {
  from: { x_percent: 0, y_percent: 0, scale: 1 },
  to: { x_percent: 3, y_percent: -1, scale: 1.05 },
});

for (const key of ['x_percent', 'y_percent', 'scale']) {
  const missingFrom = {
    parameters: {
      from: { x_percent: 0, y_percent: 0, scale: 1 },
      to: { x_percent: 1, y_percent: 1, scale: 1.02 },
    },
  };
  delete missingFrom.parameters.from[key];
  expectInvalid(missingFrom);

  const missingTo = {
    parameters: {
      from: { x_percent: 0, y_percent: 0, scale: 1 },
      to: { x_percent: 1, y_percent: 1, scale: 1.02 },
    },
  };
  delete missingTo.parameters.to[key];
  expectInvalid(missingTo);
}

expectInvalid({
  parameters: {
    from: { x_percent: '0', y_percent: 0, scale: 1 },
    to: { x_percent: 1, y_percent: 1, scale: 1.02 },
  },
});
expectInvalid({
  parameters: {
    from: { x_percent: 0, y_percent: 0, scale: NaN },
    to: { x_percent: 1, y_percent: 1, scale: 1.02 },
  },
});
expectInvalid({
  parameters: {
    from: { x_percent: 0, y_percent: 0, scale: 0 },
    to: { x_percent: 1, y_percent: 1, scale: 1.02 },
  },
});
expectInvalid({
  parameters: {
    from: { x_percent: 101, y_percent: 0, scale: 1 },
    to: { x_percent: 1, y_percent: 1, scale: 1.02 },
  },
});

console.log('HYPERFRAMES_MOTION_PARAMETER_CONTRACT=PASS');
console.log('MOTION_FALLBACK_PRESENT=false');
console.log('MISSING_PARAMETER_FAIL_CLOSED=true');
console.log('NON_NUMERIC_PARAMETER_FAIL_CLOSED=true');
