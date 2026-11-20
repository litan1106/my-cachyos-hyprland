const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../scripts/hongguo-web/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

class Element extends EventTarget {
  constructor() {
    super();
    this.children = [];
    this.textContent = '';
    this.src = '';
    this.playCount = 0;
    const classes = new Set();
    this.classList = {
      add: value => classes.add(value),
      remove: value => classes.delete(value),
      contains: value => classes.has(value),
      toggle: (value, on) => on ? classes.add(value) : classes.delete(value),
    };
  }
  set innerHTML(value) { this.children = []; }
  appendChild(child) { this.children.push(child); }
  removeAttribute(name) { if (name === 'src') this.src = ''; }
  load() {}
  pause() {}
  play() { this.playCount++; return Promise.resolve(); }
}

function player(episodes, streamFetch = async () => ({ ok: true })) {
  const elements = new Map();
  const document = new Element();
  document.querySelector = selector => {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  document.createElement = () => new Element();
  const context = vm.createContext({
    document, URL, location: { origin: 'http://127.0.0.1:8793' },
    fetch: async (url, options) => new URL(url).pathname === '/stream' ? streamFetch(url, options) : ({
      ok: true,
      json: async () => ({ items: new URL(url).pathname === '/episodes' ? episodes : [] }),
    }),
  });
  vm.runInContext(script, context);
  const video = document.querySelector('#video');
  return {
    video,
    elements,
    open: sid => vm.runInContext('openSeries', context)(sid, 'Test series'),
    close: () => vm.runInContext('closePlayer()', context),
    end: () => video.dispatchEvent(new Event('ended')),
    error: () => video.dispatchEvent(new Event('error')),
    status: () => document.querySelector('#playerStatus').textContent,
    episode: () => new URL(video.src).searchParams.get('ep'),
  };
}

test('ending an episode plays the next available episode in sorted order', async () => {
  const p = player([{ index: 8 }, { index: 2 }, { index: 5 }]);
  await p.open('series-a');
  assert.equal(p.episode(), '2');
  p.end();
  assert.equal(p.episode(), '5');
  assert.equal(p.video.playCount, 2);
  assert.equal(p.elements.get('#epbar').children[1].classList.contains('on'), true);
});

test('autoplay follows the manually selected episode', async () => {
  const p = player([{ index: 1 }, { index: 2 }, { index: 3 }]);
  await p.open('series-a');
  p.elements.get('#epbar').children[1].onclick();
  p.end();
  assert.equal(p.episode(), '3');
});

test('ending the final episode stops without looping', async () => {
  const p = player([{ index: 1 }, { index: 2 }]);
  await p.open('series-a');
  p.end();
  const count = p.video.playCount;
  p.end();
  assert.equal(p.episode(), '2');
  assert.equal(p.video.playCount, count);
});

test('a closed player ignores ended events', async () => {
  const p = player([{ index: 1 }, { index: 2 }]);
  await p.open('series-a');
  p.close();
  p.end();
  assert.equal(p.video.src, '');
  assert.equal(p.video.playCount, 1);
});

test('opening another series resets the current episode', async () => {
  const p = player([{ index: '1' }, { index: '2' }, { index: '3' }]);
  await p.open('series-a');
  p.elements.get('#epbar').children[2].onclick();
  await p.open('series-b');
  p.end();
  assert.equal(p.episode(), '2');
  assert.equal(new URL(p.video.src).searchParams.get('series_id'), 'series-b');
});

test('an empty episode list does not start playback', async () => {
  const p = player([]);
  await p.open('series-a');
  p.end();
  assert.equal(p.video.src, '');
  assert.equal(p.video.playCount, 0);
});

const flush = () => new Promise(resolve => setImmediate(resolve));

test('media errors show the stream API detail', async () => {
  let request;
  const p = player([{ index: 1 }], async (url, options) => {
    request = { url, options };
    return { ok: false, json: async () => ({ detail: 'stream失败: Upstream did not return JSON' }) };
  });
  await p.open('series-a');
  p.error();
  await flush();
  assert.match(p.status(), /stream失败: Upstream did not return JSON/);
  assert.equal(request.url, p.video.src);
  assert.equal(request.options.headers.Range, 'bytes=0-0');
});

test('successful probe cancels its body and shows a generic playback error', async () => {
  let cancelled = false;
  const p = player([{ index: 1 }], async () => ({ ok: true, body: { cancel: () => { cancelled = true; } } }));
  await p.open('series-a');
  p.error();
  await flush();
  assert.equal(cancelled, true);
  assert.match(p.status(), /播放失败/);
});

test('stale stream failures cannot replace status after switching or closing', async () => {
  let resolve;
  const p = player([{ index: 1 }, { index: 2 }], () => new Promise(r => { resolve = r; }));
  await p.open('series-a');
  p.error();
  p.elements.get('#epbar').children[1].onclick();
  resolve({ ok: false, json: async () => ({ detail: '旧错误' }) });
  await flush();
  assert.doesNotMatch(p.status(), /旧错误/);
  p.error();
  p.close();
  resolve({ ok: false, json: async () => ({ detail: '关闭后错误' }) });
  await flush();
  assert.equal(p.status(), '');
});

test('loading clears on playing and autoplay denial asks for a click', async () => {
  const p = player([{ index: 1 }]);
  p.video.play = () => Promise.reject({ name: 'NotAllowedError' });
  await p.open('series-a');
  await flush();
  assert.match(p.status(), /点击播放/);
  p.video.dispatchEvent(new Event('playing'));
  assert.equal(p.status(), '');
});

test('aborted play during switching does not show an error', async () => {
  const p = player([{ index: 1 }]);
  p.video.play = () => Promise.reject({ name: 'AbortError' });
  await p.open('series-a');
  await flush();
  assert.match(p.status(), /加载中/);
});
