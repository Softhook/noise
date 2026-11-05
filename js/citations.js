/**
 * Turns citations in note text into links to the documents, at the cited page.
 * Page numbers in the notes are PDF page numbers, so they work directly with #page=
 */

// Every way the notes name each document. A document missing from here gets no link of its own,
// and any page after its name goes to the document named before it. The tests check citations against pages.
const CITED_DOCUMENTS = [
  { name: /LCY consultation|Consultation/, file: "01_LCY_Stage3_Consultation_Document_Issue1.1.pdf", pages: 46, title: "LCY Stage 3 consultation document" },
  { name: /Annex C/, file: "02_LCY_Annex_C_Aircraft_Noise_Technical_Report.pdf", pages: 89, title: "LCY Annex C, aircraft noise technical report" },
  { name: /AEF\b/, file: "08_AEF_Noise_Lessons_for_London_City_Airport.pdf", pages: 12, title: "AEF, noise lessons for London City Airport" },
  { name: /EASA A320 sheet/, file: "09_EASA_TCDSN_A.064.3_A320_Issue42.pdf", pages: 373, title: "EASA noise data sheet, A320 family" },
  { name: /EASA ERJ 190 sheet/, file: "10_EASA_TCDSN_IM.A.071_ERJ190_Issue24.pdf", pages: 201, title: "EASA noise data sheet, ERJ 190 family" },
  { name: /EASA A220 sheet/, file: "18_EASA_TCDSN_IM.A.570_BD500_A220_Issue14.pdf", pages: 9, title: "EASA noise data sheet, A220 family" },
  { name: /EASA DHC-8 sheet/, file: "27_EASA_TCDSN_IM.A.191_DHC-8_Issue9.pdf", pages: 54, title: "EASA noise data sheet, DHC-8 family" },
  { name: /noise scheme/, file: "12_LCY_Aircraft_Noise_Categorisation_Scheme_March2022.pdf", pages: 43, title: "LCY aircraft noise categorisation scheme" },
  { name: /Stage 4\b/, file: "16_LCY_Stage4_Airspace_Change_Proposal_Issue1.0.pdf", pages: 36, title: "LCY Stage 4 airspace change proposal" },
  { name: /Stage 2\b/, file: "17_LCY_Stage2_Develop_and_Assess_V1.1.pdf", pages: 205, title: "LCY Stage 2 develop and assess" },
  { name: /Directive(?: 2015\/996)?|Doc 29/, file: "19_EU_Directive_2015-996_Doc29_Noise_Method.pdf", pages: 823, title: "Directive (EU) 2015/996, Doc 29 noise method" },
  { name: /NASA TM 83214/, file: "20_NASA_TM83214_SEL_EPNL_Duration_Coefficients.pdf", pages: 16, title: "NASA TM 83214" },
  { name: /Bickerdike Allen(?: Thamesmead survey)?/, file: "21_BAP_Aircraft_Noise_Survey_Thamesmead_Nov2024.pdf", pages: 15, title: "Bickerdike Allen Thamesmead survey" }
];
const PAGE_CITATION = /(?:(?:Figs?\.|Tables?) [\w–-]+,? )?\bpp?\.\d+(?:–\d+)?(?:, \d+(?:–\d+)?(?![\d ]*[a-zA-Z]))*/;
const CITATION_PATTERN = new RegExp(`\\b(${CITED_DOCUMENTS.map(entry => entry.name.source).join("|")})|(${PAGE_CITATION.source})`, "g");

// Splits notes into plain text and links. A page without a document name belongs to the document last named.
// A document name is only linked when no page follows it in the sentence, because then the page is the link.
function citationParts(text) {
  const parts = [];
  const addText = value => {
    if (value) parts.push({ text: value });
  };
  let doc = null;
  let last = 0;
  for (const match of text.matchAll(CITATION_PATTERN)) {
    addText(text.slice(last, match.index));
    last = match.index + match[0].length;
    if (match[1]) {
      doc = CITED_DOCUMENTS.find(entry => entry.name.test(match[1]));
      const pageFollows = /^(?:[^.]|\d\.\d|Figs?\.)*\bpp?\.\d/.test(text.slice(last));
      parts.push(pageFollows ? { text: match[0] } : { text: match[0], doc });
    } else if (!doc) {
      addText(match[0]);
    } else {
      // Each listed page is its own link, and a range opens at its first page
      let at = 0;
      for (const number of match[0].matchAll(/\d+(?:–\d+)?(?=$|, \d)/g)) {
        const start = at === 0 ? 0 : number.index;
        addText(match[0].slice(at, start));
        at = number.index + number[0].length;
        parts.push({ text: match[0].slice(start, at), doc, page: parseInt(number[0], 10) });
      }
    }
  }
  addText(text.slice(last));
  return parts;
}

function citedLink(part) {
  const link = document.createElement("a");
  link.textContent = part.text;
  link.href = `Documents/${part.doc.file}${part.page ? `#page=${part.page}` : ""}`;
  link.target = "_blank";
  link.rel = "noopener";
  link.title = `${part.doc.title}${part.page ? `, page ${part.page}` : ""}`;
  return link;
}

// Fills an element with note text, turning citations into links and **marked** words into bold
function setCitedText(element, text) {
  const nodes = [];
  let bold = false;
  const add = node => {
    if (!bold) {
      nodes.push(node);
      return;
    }
    const strong = document.createElement("strong");
    strong.append(node);
    nodes.push(strong);
  };
  for (const part of citationParts(text)) {
    if (part.doc) {
      add(citedLink(part));
      continue;
    }
    part.text.split("**").forEach((piece, i) => {
      if (i > 0) bold = !bold;
      if (piece) add(document.createTextNode(piece));
    });
  }
  element.replaceChildren(...nodes);
}
