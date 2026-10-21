// These are prepared snapshots, not classifier/extraction results computed by this site.
// Originals are imported directly from the application's fictional sample documents.
import incorrectTotal from "../../samples/incorrect-total.txt?raw";
import validInvoice from "../../samples/valid-invoice.txt?raw";
import manualContract from "../../samples/manual-contract.txt?raw";

export type Fields = {
  vendor: string;
  number: string;
  date: string;
  currency: string;
  subtotal: string;
  tax: string;
  total: string;
  line_total: string;
};
export type Sample = {
  id: string;
  name: string;
  filename: string;
  type: string;
  original: string;
  fields: Fields;
  expected: string;
};

export const samples: Sample[] = [
  {
    id: "incorrect-total", name: "Incorrect total", filename: "incorrect-total.txt", type: "invoice",
    original: incorrectTotal,
    fields: { vendor: "Ridgeway Trading", number: "RT-9912", date: "2026-08-03", currency: "USD", subtotal: "304.00", tax: "25.84", total: "349.84", line_total: "304.00" },
    expected: "304.00 + 25.84 = 329.84. Change total from 349.84 to 329.84, save and revalidate, then approve explicitly.",
  },
  {
    id: "valid-invoice", name: "Valid invoice", filename: "valid-invoice.txt", type: "invoice",
    original: validInvoice,
    fields: { vendor: "Northwind Supplies", number: "NW-2026-0481", date: "2026-08-12", currency: "USD", subtotal: "624.00", tax: "53.04", total: "677.04", line_total: "624.00" },
    expected: "The prepared fields pass these sample checks. It starts ready, but enters exports only after you click Approve sample.",
  },
  {
    id: "manual-contract", name: "Manual review", filename: "manual-contract.txt", type: "contract",
    original: manualContract,
    fields: { vendor: "Silver Birch Studio", number: "SB-014", date: "2026-08-12", currency: "USD", subtotal: "", tax: "", total: "", line_total: "" },
    expected: "Read the agreement, confirm the document type and enter a review note of at least 10 characters. Save and revalidate before approval. Invoice arithmetic does not apply.",
  },
];
