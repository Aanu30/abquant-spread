// Builds the Spread jury deck. Run: node build.js
const pptxgen = require("pptxgenjs");
const path = require("path");
// Optional theme step: set APPLY_THEME to the path of a pptx apply_theme.js helper; without it the deck is built unthemed.
const applyTheme = process.env.APPLY_THEME ? require(process.env.APPLY_THEME).applyTheme : async () => {};

const OUT = path.join(__dirname, "..", "Spread_jury_slides.pptx");

const INK = "10222B", PAPER = "F4F6F5", WHITE = "FFFFFF", TEAL = "1F6F6A", MUTED = "5E6E73", BODY = "3B4B51";
const ORANGE = "F26B21", ORANGE_LIGHT = "FF8A4C", SAGE = "8FB8B0", PANEL = "1C3641", RULE = "DDE3E1";
const HEAD = "Cambria", TEXT = "Calibri";

const THEME = {
  name: "Spread night road", headFontFace: HEAD, bodyFontFace: TEXT,
  colors: { dk1: INK, lt1: WHITE, dk2: TEAL, lt2: PAPER, accent1: ORANGE, accent2: TEAL, accent3: SAGE, accent4: MUTED, accent5: PANEL, accent6: "B34A0A", hlink: TEAL, folHlink: MUTED },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.title = "Spread: pricing a delivery like a market maker";
pres.author = "Team ABQuant";
pres.theme = { headFontFace: HEAD, bodyFontFace: TEXT };

const footer = (color) => ({ text: { text: "Spread · ABQuant · Junction 2026", options: { x: 0.5, y: 5.2, w: 5, h: 0.25, fontFace: TEXT, fontSize: 10, color, margin: 0, isTextBox: true } } });
const slideNum = (color) => ({ x: 9.0, y: 5.2, w: 0.5, h: 0.25, fontFace: TEXT, fontSize: 10, color, align: "right", margin: 0 });
const titlePh = (color) => ({ placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.35, w: 9, h: 0.8, fontFace: HEAD, fontSize: 32, bold: true, color, valign: "top", margin: 0 }, text: "" } });

pres.defineSlideMaster({ title: "TITLE", background: { color: INK }, objects: [] });
pres.defineSlideMaster({ title: "LIGHT", background: { color: PAPER }, objects: [titlePh(INK), footer(MUTED)], slideNumber: slideNum(MUTED) });
pres.defineSlideMaster({ title: "DARK", background: { color: INK }, objects: [titlePh(WHITE), footer(SAGE)], slideNumber: slideNum(SAGE) });

// ---- helpers (fresh option objects every call: pptxgenjs mutates them)
const T = (s, text, o) => s.addText(text, Object.assign({ isTextBox: true, margin: 0, fontFace: TEXT, fontSize: 14, color: BODY, valign: "top" }, o));
const card = (s, x, y, w, h, fill, name) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
  x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: RULE, width: 0.75 },
  shadow: { type: "outer", color: "000000", opacity: 0.1, blur: 6, offset: 2, angle: 90 }, objectName: name,
});
const flatCard = (s, x, y, w, h, fill, name) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: fill, width: 0.25 }, objectName: name });
const para = (text, size, color, extra) => Object.assign({ text, options: { fontSize: size, color, breakLine: true, paraSpaceAfter: 8 } }, extra || {});
const bullets = (items, size, color) => items.map((t, i) => ({ text: t, options: { bullet: true, fontSize: size, color, breakLine: i < items.length - 1, paraSpaceAfter: 6 } }));

// ================= 1. Title
{
  const s = pres.addSlide({ masterName: "TITLE" });
  T(s, "Pricing a delivery like a market maker", { x: 0.7, y: 1.2, w: 8.4, h: 1.7, fontFace: HEAD, fontSize: 42, bold: true, color: WHITE, objectName: "Title" });
  T(s, "Team ABQuant · Bahn Express “Spread” challenge · Junction 2026", { x: 0.7, y: 3.1, w: 8.4, h: 0.4, fontSize: 18, color: SAGE, objectName: "Subtitle" });
  T(s, "Built on the paper “Market Making Optimisation Theories” (A. Bhatt, 2026)", { x: 0.7, y: 3.6, w: 8.4, h: 0.35, fontSize: 14, color: "B7C7C4", objectName: "Paper credit" });
  const xs = [5.8, 6.9, 8.0, 9.1];
  for (let i = 0; i < 3; i++) s.addShape(pres.shapes.LINE, { x: xs[i] + 0.3, y: 4.6, w: 0.8, h: 0, line: { color: MUTED, width: 2, dashType: "dash" }, objectName: "Route " + (i + 1) });
  xs.forEach((x, i) => s.addShape(pres.shapes.OVAL, { x, y: 4.46, w: 0.28, h: 0.28, fill: { color: i === 3 ? ORANGE : SAGE }, line: { color: i === 3 ? ORANGE : SAGE, width: 0.5 }, objectName: "Stop " + (i + 1) }));
  s.addNotes("Say: We run a delivery company for one simulated week in Finland. We quote prices to car dealers, then hire freelance drivers to move the cars we win. Our rule for pricing comes straight from my market-making paper. The rest of the talk is four things we found in the data, what they were worth, and what did not work.");
}

// ================= 2. The problem
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  s.addText("A late car costs more than it earns", { placeholder: "title" });
  const tiles = [
    ["−€72,613", "A plain bot (the kit’s starter) in one week: only 45.5% of cars on time."],
    ["90%", "of won orders must arrive on time, or the team is not ranked at all."],
    ["12.5%", "typical margin per car. One delay of a few hours turns it into a loss."],
  ];
  tiles.forEach(([big, label], i) => {
    const x = 0.5 + i * 3.1;
    card(s, x, 1.35, 2.85, 2.2, WHITE, "Stat card " + (i + 1));
    T(s, big, { x: x + 0.2, y: 1.55, w: 2.45, h: 0.7, fontFace: HEAD, fontSize: 34, bold: true, color: i === 0 ? "B34A0A" : TEAL, objectName: "Stat " + (i + 1) });
    T(s, label, { x: x + 0.2, y: 2.35, w: 2.45, h: 1.1, fontSize: 14, objectName: "Stat label " + (i + 1) });
  });
  T(s, [
    para("What we do: quote a price to each car dealer, then post the delivery as a gig that freelance drivers can book.", 16, INK),
    para("What we can’t see: the competitor’s prices and the drivers’ real costs. We only see what we win, lose and who books.", 16, INK, { options: { fontSize: 16, color: INK, paraSpaceAfter: 0 } }),
  ], { x: 0.5, y: 3.8, w: 9, h: 1.3, objectName: "Setting" });
  s.addNotes("Say: Score is gross margin in euros, but only if at least 90 percent of the cars we win arrive on time. A plain bot that quotes the list price wins lots of cars and cannot find drivers in time, so it loses 72 thousand euros and is not ranked. Margins are thin, around 12 percent, so a late car wipes out the profit of many cars. And we are blind: we never see the competitor’s prices or what a driver would accept.");
}

// ================= 3. One rule
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  s.addText("One rule prices every quote", { placeholder: "title" });
  T(s, "price  =", { x: 0.5, y: 1.3, w: 3, h: 0.4, fontFace: HEAD, fontSize: 20, bold: true, color: INK, objectName: "Price equals" });
  const parts = [
    ["Expected driver fee", "What a driver will cost us to move this car."],
    ["Late risk", "Chance it is late, times the refund and the trust we lose."],
    ["Markup", "How much more a dealer pays before switching to the competitor."],
    ["Price of scarce drivers", "Zero until drivers in that area run short, then it rises."],
  ];
  parts.forEach(([h, d], i) => {
    const x = 0.4 + i * 2.4;
    card(s, x, 1.8, 2.0, 2.0, WHITE, "Term " + (i + 1));
    T(s, h, { x: x + 0.15, y: 1.95, w: 1.7, h: 0.6, fontFace: HEAD, fontSize: 15, bold: true, color: TEAL, objectName: "Term name " + (i + 1) });
    T(s, d, { x: x + 0.15, y: 2.6, w: 1.7, h: 1.1, fontSize: 14, objectName: "Term text " + (i + 1) });
    if (i < 3) T(s, "+", { x: x + 2.0, y: 2.55, w: 0.4, h: 0.5, fontFace: HEAD, fontSize: 28, bold: true, color: INK, align: "center", objectName: "Plus " + (i + 1) });
  });
  flatCard(s, 0.5, 4.0, 9, 1.05, "E3EBE9", "Paper link");
  T(s, "From the paper: the markup is the inverse of how fast customers walk away (Prop. 1). Each scarce resource adds its price times how much the order uses (Prop. 3), and that price is zero until the resource runs out (Prop. 4). Here the competitor’s price plays the market mid and drivers play inventory.", { x: 0.7, y: 4.1, w: 8.6, h: 0.85, fontSize: 14, color: INK, objectName: "Paper link text" });
  s.addNotes("Say: This is the first-order condition of expected profit, the same shape as the optimal spread in my paper: cost plus a markup that depends on how fast customers leave when you raise the price. Each scarce thing, here drivers, adds a price times how much the order uses of it. That price is zero while there is plenty and rises only when drivers run short. Everything else we built feeds numbers into these four boxes.");
}

// ================= 4. Flow
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  s.addText("One request, start to finish", { placeholder: "title" });
  const steps = [
    ["Price request", "A dealer asks. We have 15 world-minutes: 4.5 real seconds in the final."],
    ["Read the note", "Ready time, real opening hours, gearbox and plates, in three languages."],
    ["Choose the price", "Best price per delivery option. Decline at 4× list if no driver fits."],
    ["Wait for a partner", "Won cars wait in a pool to be paired into one driver trip."],
    ["Post the gig", "Opening fee held, then a few steps up before the deadline warning."],
    ["Rescue", "No driver yet? Raise the fee only as far as lateness would cost."],
  ];
  steps.forEach(([h, d], i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = 0.4 + col * 3.25, y = 1.35 + row * 1.9;
    card(s, x, y, 2.7, 1.65, WHITE, "Step " + (i + 1));
    s.addShape(pres.shapes.OVAL, { x: x + 0.15, y: y + 0.15, w: 0.4, h: 0.4, fill: { color: ORANGE }, line: { color: ORANGE, width: 0.5 }, objectName: "Step badge " + (i + 1) });
    T(s, String(i + 1), { x: x + 0.15, y: y + 0.15, w: 0.4, h: 0.4, fontFace: HEAD, fontSize: 14, bold: true, color: INK, align: "center", valign: "middle", objectName: "Step number " + (i + 1) });
    T(s, h, { x: x + 0.7, y: y + 0.17, w: 1.9, h: 0.4, fontFace: HEAD, fontSize: 15, bold: true, color: INK, valign: "middle", objectName: "Step name " + (i + 1) });
    T(s, d, { x: x + 0.15, y: y + 0.7, w: 2.4, h: 0.9, fontSize: 14, objectName: "Step text " + (i + 1) });
    if (col < 2) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 2.76, y: y + 0.65, w: 0.4, h: 0.3, fill: { color: SAGE }, line: { color: SAGE, width: 0.25 }, objectName: "Arrow " + (i + 1) });
  });
  T(s, "Every price is logged with its four terms, so any quote or decline can be read line by line.", { x: 0.5, y: 4.75, w: 9, h: 0.35, fontSize: 14, color: INK, objectName: "Clarity line" });
  s.addNotes("Say: This is what the desk does for every request. It reads the dealer’s note first, because the world obeys the note whether we read it or not. It prices each delivery option, and if no driver could make it on time it quotes four times the list price, which loses on purpose. Won cars wait briefly to be paired, then are posted with a fee that starts low and steps up. If no driver books, we rescue. Every quote is logged with the four terms, so the jury can follow any decision.");
}

// ================= 5. Idea 1: pairs
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  s.addText("Idea 1 · Two cars, one driver trip", { placeholder: "title" });
  T(s, [
    para("A driver’s cost is time at the wheel, the trip to the first pickup and the trip home. A second car that starts where the first ends removes a trip.", 16, INK),
    para("How we know: a fork experiment replayed the same future and posted the same cars two ways. Pairs booked at 0.65–0.80 of two typical fees. Single cars needed 0.9 and more.", 14, BODY),
    para("Won cars wait in a pool for a partner (up to an hour for same-day cars), then go out as one four-stop gig.", 14, BODY, { options: { fontSize: 14, color: BODY, paraSpaceAfter: 0 } }),
  ], { x: 0.5, y: 1.35, w: 4.4, h: 3.5, objectName: "Pairs text" });
  const tiles = [
    ["0.76×", "typical fee per car in a pair, against 1.08–1.30× for a car alone"],
    ["280 of 440", "cars a week go out in pairs"],
    ["+€1,640", "margin a week from pairing (13,292 → 14,933)"],
  ];
  tiles.forEach(([big, label], i) => {
    const y = 1.35 + i * 1.2;
    card(s, 5.2, y, 4.3, 1.05, WHITE, "Pair stat " + (i + 1));
    T(s, big, { x: 5.4, y: y + 0.1, w: 2.1, h: 0.85, fontFace: HEAD, fontSize: 26, bold: true, color: TEAL, valign: "middle", objectName: "Pair number " + (i + 1) });
    T(s, label, { x: 7.55, y: y + 0.1, w: 1.8, h: 0.85, fontSize: 12, valign: "middle", objectName: "Pair label " + (i + 1) });
  });
  s.addNotes("Say: Freelance drivers are paid for their time and their trip home. If two cars line up, one driver can do both and skips a trip home, so they accept less per car. We tested it properly: replay exactly the same week and post the same cars as pairs and as singles. Pairs got booked at about three quarters of the single-car fee. About 280 of the 440 cars a week now go out as pairs. This was our biggest single gain, about 1,600 euros a week.");
}

// ================= 6. Idea 2: far drivers
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  s.addText("Idea 2 · Drivers travel far for a gig", { placeholder: "title" });
  T(s, [
    para("Drivers are only notified of a gig within 30 km of its first pickup, so we first counted only those drivers.", 16, INK),
    para("The data said otherwise. In 2,642 bookings, only 40% of the drivers who took a gig lived inside that circle. The median driver lived 64 km from the pickup.", 14, BODY, { options: { fontSize: 14, color: BODY, paraSpaceAfter: 0 } }),
  ], { x: 0.5, y: 1.35, w: 4.3, h: 2.2, objectName: "Far drivers text" });
  card(s, 0.5, 3.75, 4.3, 1.1, WHITE, "Far drivers stat");
  T(s, "+€2,448", { x: 0.7, y: 3.85, w: 1.9, h: 0.9, fontFace: HEAD, fontSize: 26, bold: true, color: TEAL, valign: "middle", objectName: "Far drivers number" });
  T(s, "a week, better in 12 of 12 weeks, after counting drivers beyond 30 km", { x: 2.65, y: 3.85, w: 2.0, h: 0.9, fontSize: 12, valign: "middle", objectName: "Far drivers label" });
  s.addChart(pres.charts.BAR, [{ name: "Bookings", labels: ["Hyvinkää drivers", "Helsinki, Vantaa, Espoo", "Other towns"], values: [40, 179, 119] }], {
    x: 5.1, y: 1.3, w: 4.5, h: 3.5, barDir: "bar", catAxisOrientation: "maxMin", valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    chartColors: [SAGE, TEAL, SAGE], showLegend: false, showTitle: true, title: "Who booked gigs starting in Hyvinkää (338 bookings)", titleFontSize: 14, titleColor: INK, titleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelColor: INK, dataLabelFontFace: "+mn-lt", catAxisLabelFontSize: 12, catAxisLabelColor: BODY, catAxisLabelFontFace: "+mn-lt", barGapWidthPct: 60,
  });
  s.addNotes("Say: The app only notifies drivers within 30 kilometres of the pickup, so we assumed only those drivers mattered. When we checked 2,642 real bookings, only 40 percent of the drivers who booked lived inside that circle. Take Hyvinkää: of 338 bookings, only 40 were by local drivers and 179 were by drivers from Helsinki, Vantaa and Espoo, 50 to 65 kilometres away. Our driver budget wrongly called those towns full, so we refused about 240 requests a week. Counting far drivers at a discount fixed that, and it helped in all 12 test weeks.");
}

// ================= 7. Idea 3: on-time brake
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  s.addText("Idea 3 · Stop when drivers run out", { placeholder: "title" });
  T(s, "Same-day cars we won on days when drivers ran out", { x: 0.5, y: 1.3, w: 9, h: 0.35, fontSize: 16, bold: true, color: INK, objectName: "Brake heading" });
  const tiles = [["4–7%", "late when fewer than 9 cars had sat unbooked for an hour", WHITE], ["25%", "late with 13 to 20 such cars", "FCE4D6"], ["60%", "late with more than 20 such cars", "F7C9AC"]];
  tiles.forEach(([big, label, fill], i) => {
    const x = 0.5 + i * 3.1;
    card(s, x, 1.8, 2.85, 1.6, fill, "Late tile " + (i + 1));
    T(s, big, { x: x + 0.2, y: 1.9, w: 2.45, h: 0.7, fontFace: HEAD, fontSize: 34, bold: true, color: INK, objectName: "Late number " + (i + 1) });
    T(s, label, { x: x + 0.2, y: 2.6, w: 2.45, h: 0.75, fontSize: 14, color: INK, objectName: "Late label " + (i + 1) });
  });
  flatCard(s, 0.5, 3.65, 9, 1.45, "E3EBE9", "Brake fix");
  T(s, [
    para("The fix: the count of waiting cars now raises a same-day car’s late risk, 2 points per car beyond four.", 16, INK),
    para("On 24 weeks: +€359 a week, and the worst week went from 90.4% to 94.1% on time. The gate is 90%.", 16, INK, { options: { fontSize: 16, color: INK, paraSpaceAfter: 0 } }),
  ], { x: 0.7, y: 3.78, w: 8.6, h: 1.25, objectName: "Brake fix text" });
  s.addNotes("Say: Twelve fresh weeks showed the bot made money but one week fell to 90.4 percent on time, right at the ranking line. The logs showed why: on days when drivers ran out, we kept winning same-day cars. When more than 20 cars sat unbooked, 60 percent of the same-day cars were late. So the number of waiting cars is now part of the late risk, and the quote rises, which loses those cars on purpose. The worst week went from 90.4 to 94.1 percent and the average margin went up too.");
}

// ================= 8. Idea 4: notes and the kind of day
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  s.addText("Idea 4 · Read every note", { placeholder: "title" });
  T(s, [
    para("Dealers write notes in Finnish, Swedish and English, with typos and corrections: ready times, real opening hours, tighter deadlines, gearbox, plates, tyres.", 14, INK),
    para("The world obeys a note whether or not we read it. A missed note is a failed visit we pay for. The kit’s starter reads only clock times near a few keywords.", 14, BODY, { options: { fontSize: 14, color: BODY, paraSpaceAfter: 0 } }),
  ], { x: 0.5, y: 1.35, w: 5.2, h: 1.9, objectName: "Notes text" });
  const mini = [["99.8%", "of ready times read correctly, checked against the revealed truth"], ["100%", "of deadlines, opening hours, gearbox, plates and tyres"], ["+€2,300", "a week, about, with the driver-day rules the notes feed"]];
  mini.forEach(([big, label], i) => {
    const x = 0.5 + i * 1.75;
    card(s, x, 3.3, 1.6, 1.7, WHITE, "Notes stat " + (i + 1));
    T(s, big, { x: x + 0.12, y: 3.4, w: 1.4, h: 0.5, fontFace: HEAD, fontSize: 20, bold: true, color: TEAL, objectName: "Notes number " + (i + 1) });
    T(s, label, { x: x + 0.12, y: 3.95, w: 1.4, h: 1.0, fontSize: 12, objectName: "Notes label " + (i + 1) });
  });
  flatCard(s, 6.0, 1.35, 3.5, 3.65, "E3EBE9", "Day panel");
  T(s, "Which kind of day is it?", { x: 6.2, y: 1.5, w: 3.1, h: 0.4, fontFace: HEAD, fontSize: 16, bold: true, color: INK, objectName: "Day heading" });
  T(s, [
    para("Every level-8 week has one price-war day (competitor 20% cheaper) and one outage day (competitor down in one region).", 14, INK),
    para("A Bayesian detector updates the odds from every win and loss, and prices follow.", 14, INK),
    para("+€460 a week. It finds both days in all six tuning weeks.", 14, INK, { options: { bold: true, fontSize: 14, color: INK, paraSpaceAfter: 0 } }),
  ], { x: 6.2, y: 2.0, w: 3.1, h: 2.9, objectName: "Day text" });
  s.addNotes("Say: Many requests carry a note from the dealer, in Finnish, Swedish or English, sometimes with typos or a correction. If we ignore it, the driver arrives too early or too late and we pay for a failed visit. Our reader matches the revealed truth on 99.8 percent of ready times and all the other fields. Separately, every level-8 week has a price-war day and an outage day that nobody announces. We watch the day’s wins and losses and update the odds with Bayes’ rule, so prices follow within hours.");
}

// ================= 9. Results
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  s.addText("Results: practice vs unseen weeks", { placeholder: "title" });
  const labels = ["Price rule only", "+ Driver budget by town", "+ Few-step fee schedule", "+ Driver’s workable day", "+ Own note reader", "+ Price-war detector", "+ Two cars per gig", "+ Drivers beyond 30 km", "+ Live brake, tighter budget"];
  const values = [-2804, 3803, 5491, 9072, 11370, 11828, 14933, 16020, 16675];
  s.addChart(pres.charts.BAR, [{ name: "Margin per week", labels, values }], {
    x: 0.4, y: 1.25, w: 5.7, h: 3.5, barDir: "bar", catAxisOrientation: "maxMin", valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    chartColors: [SAGE, SAGE, SAGE, SAGE, SAGE, SAGE, SAGE, SAGE, TEAL], showLegend: false, showTitle: true, title: "Mean margin per practice week (€), steps added one by one", titleFontSize: 13, titleColor: INK, titleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "#,##0", dataLabelFontSize: 11, dataLabelColor: INK, dataLabelFontFace: "+mn-lt", catAxisLabelFontSize: 11, catAxisLabelColor: BODY, catAxisLabelFontFace: "+mn-lt", barGapWidthPct: 40,
  });
  T(s, "Steps are cumulative. Early steps measured on 6 practice weeks, the last on 24 (12 never used for tuning). The kit’s starter: −€72,613 on one week.", { x: 0.5, y: 4.8, w: 9, h: 0.35, fontSize: 10, color: MUTED, objectName: "Chart note" });
  flatCard(s, 6.3, 1.3, 3.3, 3.4, "E3EBE9", "Unseen panel");
  T(s, "On weeks we had never seen", { x: 6.5, y: 1.42, w: 2.95, h: 0.35, fontFace: HEAD, fontSize: 15, bold: true, color: INK, objectName: "Unseen heading" });
  const FINAL_RESULT = process.env.FINAL_RESULT || "The final: [result to add after it ends]";
  T(s, bullets([
    "00:00 round: €16,053 a week, 96.6% on time, 17th of 59 ranked",
    "03:00 round: €15,270, 95.9%, 13th of 49 ranked",
    "06:00 round, final version: €15,384, 97.0%, 8th of 36 ranked so far",
    "Live rehearsal at final speed: €14,867, 97.0%. Killed twice and restarted: €13,883, still ranked",
    FINAL_RESULT,
  ], 12, INK), { x: 6.5, y: 1.85, w: 3.0, h: 2.8, objectName: "Unseen list" });
  s.addNotes("Say: Each bar adds one idea on top of the last, measured on the same practice weeks, so the difference is the idea and nothing else. We went from losing 72 thousand euros to about 16,700 a week in practice. On weeks nobody on the team had seen, the public ranking rounds gave about 15 to 16 thousand a week with 96 percent on time. The bot also survived rehearsals where we killed it twice mid-week. The bot playing the final is the last version, which adds a small capped price for long hauls when drivers are over budget: about +€84 a week over 86 test weeks. The ranking-round places were read at 07:00 and can still move; the last bullet is the final’s own result.");
}

// ================= 10. What failed
{
  const s = pres.addSlide({ masterName: "DARK" });
  s.addText("What failed, what we don’t know", { placeholder: "title" });
  const cols = [
    ["Tried and dropped", [
      "Discounts to build dealer trust: about −€900 a week",
      "Offers to drivers near the delivery end: 4 accepted of 666",
      "Fee steps by gig age: −€900 to −€1,700 a week",
      "Refitting on our own weeks: −€400 (selection bias)",
    ]],
    ["What we don’t know", [
      "The competitor’s real prices: estimated from our own wins and losses",
      "Drivers’ real costs: seen only through bookings and fees",
      "The exact shape of dealer acceptance",
    ]],
    ["What would break it", [
      "A week with far fewer drivers than any practice week. Our worst practice week was 94.1% on time; the line is 90%",
      "Week-to-week luck: the 03:00 round’s weeks ranged from €11,198 to €20,318",
    ]],
  ];
  cols.forEach(([h, items], i) => {
    const x = 0.4 + i * 3.1;
    flatCard(s, x, 1.3, 2.9, 3.55, PANEL, "Fail card " + (i + 1));
    T(s, h, { x: x + 0.2, y: 1.45, w: 2.5, h: 0.4, fontFace: HEAD, fontSize: 16, bold: true, color: ORANGE_LIGHT, objectName: "Fail heading " + (i + 1) });
    T(s, bullets(items, 14, PAPER), { x: x + 0.2, y: 1.95, w: 2.55, h: 2.8, objectName: "Fail list " + (i + 1) });
  });
  s.addNotes("Say: We kept a table of everything that lost money, and each one can be switched back on. The biggest surprise was dealer trust: it looks like a good investment to discount early, but drivers are the scarce thing, so a discounted order takes a driver from a full-price order. Be honest about what we cannot see: the competitor’s prices, drivers’ real costs and the shape of dealer acceptance are all estimated. The main risk is a week with far fewer drivers than anything we practised on.");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("written", OUT);
})();
