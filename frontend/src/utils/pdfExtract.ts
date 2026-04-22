import * as pdfjsLib from "pdfjs-dist";
import PdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?worker";
import type { TextItem, TextMarkedContent } from "pdfjs-dist/types/src/display/api";

// Configure the worker once: Vite's `?worker` import gives us a Worker
// constructor with the worker code bundled in, avoiding the brittle
// dynamic-import-by-URL path that fails in some browsers.
pdfjsLib.GlobalWorkerOptions.workerPort = new PdfWorker();

function isTextItem(item: TextItem | TextMarkedContent): item is TextItem {
  return "str" in item && typeof (item as TextItem).str === "string";
}

export async function extractPdfText(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const loadingTask = pdfjsLib.getDocument({ data: new Uint8Array(buffer) });
  const pdf = await loadingTask.promise;

  const pageTexts: string[] = [];
  try {
    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
      const page = await pdf.getPage(pageNum);
      const content = await page.getTextContent();
      const text = content.items
        .filter(isTextItem)
        .map((item) => item.str)
        .join(" ");
      pageTexts.push(text);
      page.cleanup();
    }
  } finally {
    await pdf.cleanup();
    await pdf.destroy();
  }

  return pageTexts.join("\n\n").trim();
}
