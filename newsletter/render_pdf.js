// 사용법: node render_pdf.js <입력.html> <출력.pdf>
// 미리 설치된 playwright(chromium)로 HTML을 A4 PDF로 변환한다.
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const [, , input, output] = process.argv;
  if (!input || !output) {
    console.error('usage: node render_pdf.js <input.html> <output.pdf>');
    process.exit(2);
  }
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto('file://' + path.resolve(input), { waitUntil: 'load' });
    await page.pdf({ path: output, format: 'A4', printBackground: true, preferCSSPageSize: true });
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
