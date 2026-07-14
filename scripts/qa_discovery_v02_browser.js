/**
 * Headless smoke QA for discovery-taxonomy-v02 mirror.
 * Usage: node scripts/qa_discovery_v02_browser.js
 */
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");

const BASE =
  process.env.QA_BASE ||
  "http://127.0.0.1:8790/docs/field-desk-map-deploy/discovery-taxonomy-v02/index.html";
const OUT = path.join("/tmp", "discovery-v02-qa.json");
const SCREEN_DESK = "/opt/cursor/artifacts/discovery-v02-desktop.png";
const SCREEN_MOBILE = "/opt/cursor/artifacts/discovery-v02-mobile.png";

function get(url) {
  return new Promise((resolve, reject) => {
    http
      .get(url, (res) => {
        let data = "";
        res.on("data", (c) => (data += c));
        res.on("end", () => resolve({ status: res.statusCode, data }));
      })
      .on("error", reject);
  });
}

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const report = {
    desktop: null,
    mobile: null,
    overlay: null,
    existing_profile: null,
    incognito: null,
    errors: [],
  };

  let puppeteer;
  try {
    puppeteer = require("puppeteer-core");
  } catch {
    try {
      puppeteer = require("puppeteer");
    } catch (e) {
      report.errors.push("puppeteer unavailable: " + e.message);
      fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
      console.log(JSON.stringify(report, null, 2));
      process.exit(1);
    }
  }

  fs.mkdirSync("/opt/cursor/artifacts", { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME_PATH || "/usr/local/bin/google-chrome",
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--window-size=1280,900"],
  });

  async function runViewport(label, width, height, screenshotPath) {
    const page = await browser.newPage();
    await page.setViewport({ width, height, isMobile: width < 600, hasTouch: width < 600 });
    const url = `${BASE}?v=discovery-taxonomy-v02&resetFilters=1`;
    const consoleErrors = [];
    page.on("pageerror", (err) => consoleErrors.push(String(err)));
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    await page.goto(url, { waitUntil: "networkidle2", timeout: 120000 });
    await delay(4000);

    const result = await page.evaluate(() => {
      const labels = Array.from(document.querySelectorAll("#layersPanel .check span")).map((el) =>
        (el.textContent || "").trim()
      );
      const exploreBtn = document.getElementById("explore-more-toggle");
      const explorePanel = document.getElementById("explore-more-panel");
      const brand = document.getElementById("brandCount");
      const indexStatus = document.getElementById("indexStatus");
      const status = document.getElementById("status");
      const modeMajor = document.getElementById("modeMajor");
      const overlayBlock = document.getElementById("approvedPublicOverlaysBlock");
      const hasDiscovery = !!(window.NYCIF_DISCOVERY_V02 && window.NYCIF_DISCOVERY_V02.feedRoot === "schema-v1-discovery");
      return {
        hasDiscovery,
        brandText: brand ? brand.textContent : null,
        statusText: status ? status.textContent : null,
        indexText: indexStatus ? indexStatus.textContent : null,
        majorActive: modeMajor ? modeMajor.classList.contains("active") : false,
        labels,
        hasKids: labels.some((t) => t.includes("Kids / family")),
        hasClasses: labels.some((t) => t.includes("Classes / workshops")),
        hasVolunteer: labels.some((t) => t.includes("Volunteer")),
        hasParksOutdoors: labels.some((t) => t.includes("Parks / outdoors")),
        hasExplore: !!(exploreBtn && /Explore More/.test(exploreBtn.textContent || "")),
        exploreExpanded: exploreBtn ? exploreBtn.getAttribute("aria-expanded") : null,
        explorePanelHidden: explorePanel ? explorePanel.hidden : null,
        overlayMounted: !!overlayBlock,
        overlayLabels: overlayBlock
          ? Array.from(overlayBlock.querySelectorAll("label")).map((l) => (l.textContent || "").trim())
          : [],
      };
    });

    // Open filters panel so Explore More is visible, then toggle it.
    try {
      const layersBtn = await page.$("#layersBtn");
      if (layersBtn) {
        await layersBtn.click();
        await delay(400);
      }
    } catch (_) {}
    if (await page.$("#explore-more-toggle")) {
      try {
        await page.click("#explore-more-toggle");
        await delay(300);
      } catch (e) {
        // Mobile may keep panel offscreen; evaluate click instead.
        await page.evaluate(() => document.getElementById("explore-more-toggle")?.click());
        await delay(300);
      }
    }
    const exploreAfter = await page.evaluate(() => {
      const exploreBtn = document.getElementById("explore-more-toggle");
      const explorePanel = document.getElementById("explore-more-panel");
      return {
        aria: exploreBtn ? exploreBtn.getAttribute("aria-expanded") : null,
        hidden: explorePanel ? explorePanel.hidden : null,
        toursVisible: explorePanel && !explorePanel.hidden
          ? /Tours \/ history/.test(explorePanel.textContent || "")
          : false,
      };
    });

    let overlayInteraction = { attempted: false, checked: false, statusAfter: null };
    try {
      // layers panel already opened above
      const checkbox = await page.$("#approvedOverlayActive5pm");
      if (checkbox) {
        overlayInteraction.attempted = true;
        await page.evaluate(() => document.getElementById("approvedOverlayActive5pm")?.click());
        await delay(2500);
        overlayInteraction.checked = await page.$eval("#approvedOverlayActive5pm", (el) => el.checked);
        overlayInteraction.statusAfter = await page.$eval("#status", (el) => el.textContent);
      }
    } catch (e) {
      overlayInteraction.error = String(e);
    }

    await page.screenshot({ path: screenshotPath, fullPage: false });
    await page.close();
    return { label, result, exploreAfter, overlayInteraction, consoleErrors: consoleErrors.slice(0, 20) };
  }

  report.desktop = await runViewport("desktop", 1280, 900, SCREEN_DESK);
  report.mobile = await runViewport("mobile", 390, 844, SCREEN_MOBILE);

  // Existing-profile simulation
  const page2 = await browser.newPage();
  await page2.goto(`${BASE}?v=discovery-taxonomy-v02`, { waitUntil: "networkidle2", timeout: 120000 });
  await delay(2500);
  report.existing_profile = await page2.evaluate(() => ({
    majorActive: document.getElementById("modeMajor")?.classList.contains("active"),
    version: window.NYCIF_DISCOVERY_V02?.version || null,
    storage: localStorage.getItem("nycif-field-desk-state-v06-safe"),
  }));
  await page2.close();

  // Incognito-like fresh context
  const ctx = await browser.createBrowserContext();
  const page3 = await ctx.newPage();
  await page3.goto(`${BASE}?v=discovery-taxonomy-v02&resetFilters=1`, {
    waitUntil: "networkidle2",
    timeout: 120000,
  });
  await delay(2500);
  report.incognito = await page3.evaluate(() => ({
    majorActive: document.getElementById("modeMajor")?.classList.contains("active"),
    version: window.NYCIF_DISCOVERY_V02?.version || null,
    brand: document.getElementById("brandCount")?.textContent || null,
  }));
  await page3.close().catch(() => {});
  await ctx.close().catch(() => {});

  await browser.close().catch(() => {});

  const pass =
    report.desktop?.result?.hasDiscovery &&
    report.desktop?.result?.hasKids &&
    report.desktop?.result?.hasClasses &&
    report.desktop?.result?.hasVolunteer &&
    report.desktop?.result?.hasParksOutdoors &&
    report.desktop?.result?.hasExplore &&
    report.desktop?.result?.majorActive &&
    report.mobile?.result?.hasKids &&
    report.incognito?.majorActive;

  report.pass = !!pass;
  report.screenshots = { desktop: SCREEN_DESK, mobile: SCREEN_MOBILE };
  fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
  fs.mkdirSync("/workspace/data", { recursive: true });
  fs.writeFileSync(
    "/workspace/data/events_discovery_v02_browser_qa.json",
    JSON.stringify(report, null, 2) + "\n"
  );
  console.log(JSON.stringify(report, null, 2));
  process.exit(pass ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
