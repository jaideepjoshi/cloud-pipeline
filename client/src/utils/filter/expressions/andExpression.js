/*
 * Copyright 2017-2019 EPAM Systems, Inc. (https://www.epam.com/)
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import FilterExpression from './filterExpression';

export default class AndExpression extends FilterExpression {
  constructor (left, right, options) {
    super(undefined, undefined, FilterExpression.types.AND, undefined, left, right, options);
  }

  get left () {
    if (this.expressions && this.expressions.length > 0) {
      return this.expressions[0];
    }
    return null;
  }

  get right () {
    if (this.expressions && this.expressions.length > 1) {
      return this.expressions[1];
    }
    return null;
  }

  toStringExpression () {
    return `(${this.left ? this.left.toStringExpression() : ''} and ${this.right ? this.right.toStringExpression() : ''})`;
  }

}
