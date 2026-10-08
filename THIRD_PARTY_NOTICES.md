# Third-party notices

`src/ledgerlight/resources/chart.html` bundles the JavaScript packages below
(Vega, Vega-Lite, Vega-Embed and their runtime dependencies). The list is the
module set of the `scripts/build-mcp-chart.mjs` bundle built from
`web/pnpm-lock.yaml`. Each package keeps its own license; ledgerlight itself is
MIT licensed (see LICENSE).

| Package | Version | License | Copyright | Text |
|---|---|---|---|---|
| d3-array | 3.2.4 | ISC | Copyright 2010-2023 Mike Bostock | [1](#license-text-1) |
| d3-color | 3.1.0 | ISC | Copyright 2010-2022 Mike Bostock | [1](#license-text-1) |
| d3-delaunay | 6.0.4 | ISC | Copyright 2018-2021 Observable, Inc.; Copyright 2021 Mapbox | [1](#license-text-1) |
| d3-dispatch | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock | [1](#license-text-1) |
| d3-dsv | 3.0.1 | ISC | Copyright 2013-2021 Mike Bostock | [1](#license-text-1) |
| d3-ease | 3.0.1 | BSD-3-Clause | Copyright 2010-2021 Mike Bostock; Copyright 2001 Robert Penner | [2](#license-text-2) |
| d3-force | 3.0.0 | ISC | Copyright 2010-2021 Mike Bostock | [1](#license-text-1) |
| d3-format | 3.1.2 | ISC | Copyright 2010-2026 Mike Bostock | [1](#license-text-1) |
| d3-geo-projection | 4.0.0 | ISC | Copyright 2013-2021 Mike Bostock | [3](#license-text-3) |
| d3-geo | 3.1.1 | ISC | Copyright 2010-2024 Mike Bostock | [4](#license-text-4) |
| d3-hierarchy | 3.1.2 | ISC | Copyright 2010-2021 Mike Bostock | [1](#license-text-1) |
| d3-interpolate | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock | [1](#license-text-1) |
| d3-path | 3.1.0 | ISC | Copyright 2015-2022 Mike Bostock | [1](#license-text-1) |
| d3-quadtree | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock | [1](#license-text-1) |
| d3-scale-chromatic | 3.1.0 | ISC | Copyright 2010-2024 Mike Bostock | [5](#license-text-5) |
| d3-scale | 4.0.2 | ISC | Copyright 2010-2021 Mike Bostock | [1](#license-text-1) |
| d3-shape | 3.2.0 | ISC | Copyright 2010-2022 Mike Bostock | [1](#license-text-1) |
| d3-time-format | 4.1.0 | ISC | Copyright 2010-2021 Mike Bostock | [1](#license-text-1) |
| d3-time | 3.1.0 | ISC | Copyright 2010-2022 Mike Bostock | [1](#license-text-1) |
| d3-timer | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock | [1](#license-text-1) |
| delaunator | 5.1.0 | ISC | Copyright (c) 2026, Mapbox | [6](#license-text-6) |
| internmap | 2.0.3 | ISC | Copyright 2021 Mike Bostock | [1](#license-text-1) |
| json-stringify-pretty-compact | 4.0.0 | MIT | Copyright (c) 2014, 2016, 2017, 2019, 2021, 2022 Simon Lydell | [7](#license-text-7) |
| robust-predicates | 3.0.3 | Unlicense | (public domain dedication) | [8](#license-text-8) |
| topojson-client | 3.1.0 | ISC | Copyright 2012-2019 Michael Bostock | [1](#license-text-1) |
| vega-canvas | 2.0.0 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-crossfilter | 5.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-dataflow | 6.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-embed | 7.3.0 | BSD-3-Clause | Copyright (c) 2015, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-encode | 5.2.2 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-event-selector | 4.0.0 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-expression | 6.1.0 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-expression | 6.2.2 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-force | 5.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-format | 2.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-functions | 6.2.0 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-geo | 5.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-hierarchy | 5.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-interpreter | 2.3.2 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-label | 2.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-lite | 6.4.3 | BSD-3-Clause | Copyright (c) 2015, University of Washington Interactive Data Lab. | [9](#license-text-9) |
| vega-loader | 5.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-parser | 7.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-projection | 2.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-regression | 2.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-runtime | 7.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-scale | 8.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-scenegraph | 5.3.0 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-schema-url-parser | 3.0.2 | BSD-3-Clause | Copyright (c) 2017, Vega | [10](#license-text-10) |
| vega-selections | 6.1.5 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-statistics | 2.0.0 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-themes | 3.0.0 | BSD-3-Clause | Copyright (c) 2016, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-time | 3.3.0 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-tooltip | 1.1.0 | BSD-3-Clause | Copyright 2016 Interactive Data Lab and contributors | [11](#license-text-11) |
| vega-transforms | 5.2.2 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-util | 2.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-view-transforms | 5.2.2 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-view | 6.2.0 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-voronoi | 5.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega-wordcloud | 5.1.3 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| vega | 6.4.0 | BSD-3-Clause | Copyright (c) 2015-2023, University of Washington Interactive Data Lab | [9](#license-text-9) |
| fast-json-patch (inlined in vega-embed build) | 3.1.1 | MIT | Copyright (c) 2013, 2014, 2020 Joachim Wester | [12](#license-text-12) |
| semver (inlined in vega-embed build) | 7.8.5 | ISC | Copyright (c) Isaac Z. Schlueter and Contributors | [13](#license-text-13) |

## License texts

Each distinct license text appears once. Copyright lines are listed per package
in the table above and apply to the matching text.

### License text 1

ISC. Applies to: d3-array@3.2.4, d3-color@3.1.0, d3-delaunay@6.0.4, d3-dispatch@3.0.1, d3-dsv@3.0.1, d3-force@3.0.0, d3-format@3.1.2, d3-hierarchy@3.1.2, d3-interpolate@3.0.1, d3-path@3.1.0, d3-quadtree@3.0.1, d3-scale@4.0.2, d3-shape@3.2.0, d3-time-format@4.1.0, d3-time@3.1.0, d3-timer@3.0.1, internmap@2.0.3, topojson-client@3.1.0.

```text
Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

### License text 2

BSD-3-Clause. Applies to: d3-ease@3.0.1.

```text
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the author nor the names of contributors may be used to
  endorse or promote products derived from this software without specific prior
  written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### License text 3

ISC. Applies to: d3-geo-projection@4.0.0.

```text
Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.

MIT License for https://github.com/scijs/integrate-adaptive-simpson

The MIT License (MIT)

Copyright 2015 Ricky Reusser

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

### License text 4

ISC. Applies to: d3-geo@3.1.1.

```text
Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.

This license applies to GeographicLib, versions 1.12 and later.

Copyright 2008-2012 Charles Karney

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### License text 5

ISC. Applies to: d3-scale-chromatic@3.1.0.

```text
Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.

Apache-Style Software License for ColorBrewer software and ColorBrewer Color Schemes

Copyright 2002 Cynthia Brewer, Mark Harrower, and The Pennsylvania State University

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License. You may obtain a copy of the
License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
```

### License text 6

ISC. Applies to: delaunator@5.1.0.

```text
ISC License


Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

### License text 7

MIT. Applies to: json-stringify-pretty-compact@4.0.0.

```text
The MIT License (MIT)


Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

### License text 8

Unlicense. Applies to: robust-predicates@3.0.3.

```text
This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <http://unlicense.org>
```

### License text 9

BSD-3-Clause. Applies to: vega-canvas@2.0.0, vega-crossfilter@5.1.3, vega-dataflow@6.1.3, vega-embed@7.3.0, vega-encode@5.2.2, vega-event-selector@4.0.0, vega-expression@6.1.0, vega-expression@6.2.2, vega-force@5.1.3, vega-format@2.1.3, vega-functions@6.2.0, vega-geo@5.1.3, vega-hierarchy@5.1.3, vega-interpreter@2.3.2, vega-label@2.1.3, vega-lite@6.4.3, vega-loader@5.1.3, vega-parser@7.1.3, vega-projection@2.1.3, vega-regression@2.1.3, vega-runtime@7.1.3, vega-scale@8.1.3, vega-scenegraph@5.3.0, vega-selections@6.1.5, vega-statistics@2.0.0, vega-themes@3.0.0, vega-time@3.3.0, vega-transforms@5.2.2, vega-util@2.1.3, vega-view-transforms@5.2.2, vega-view@6.2.0, vega-voronoi@5.1.3, vega-wordcloud@5.1.3, vega@6.4.0.

```text
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors
  may be used to endorse or promote products derived from this software
  without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### License text 10

BSD-3-Clause. Applies to: vega-schema-url-parser@3.0.2.

```text
BSD 3-Clause License

All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### License text 11

BSD-3-Clause. Applies to: vega-tooltip@1.1.0.

```text
Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### License text 12

MIT. Applies to: fast-json-patch@3.1.1.

```text
(The MIT License)


Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
'Software'), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### License text 13

ISC. Applies to: semver@7.8.5.

```text
The ISC License


Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR
IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

## Adapted code and embedded attributions

These notices appear inside the bundled package sources above and are kept here
because the minified bundle drops ordinary comments.

- vega-embed 7.3.0 (`build/embed.js`) contains code "based on
  https://github.com/epoberezkin/fast-deep-equal", marked "MIT License,
  Copyright (c) 2017 Evgeny Poberezkin", with the MIT permission text inline
  (same terms as the MIT text above).
- vega-lite 6.4.3 (`build/index.js`) contains functions "Adapted from
  https://github.com/epoberezkin/fast-deep-equal" and "Adapted from
  https://github.com/epoberezkin/fast-json-stable-stringify". The vega-lite
  package does not ship those upstream license files.
- vega-themes 3.0.0 (`build/index.js`) contains a theme marked "Copyright 2020
  Google LLC. Use of this source code is governed by a BSD-style license that can
  be found in the LICENSE file or at https://developers.google.com/open-source/licenses/bsd".
- The fast-json-patch code in vega-embed includes a TypeScript `__extends` helper
  emitted by the TypeScript compiler.
