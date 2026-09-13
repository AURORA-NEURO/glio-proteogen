import { expect, test, type Page, type Route } from "@playwright/test";

import {
  algorithmProfile,
  analysisResult,
  demoRequest,
  verificationResult,
} from "../fixtures/proteogenomic-state";
import {
  gbmAlgorithmProfile,
  gbmAnalysisResult,
  gbmDemoRequest,
  gbmVerificationResult,
} from "../fixtures/gbm-proteomic-axes";
import {
  neftelAnalysisResult,
  neftelDemoRequest,
  neftelProfile,
  neftelVerification,
} from "../fixtures/neftel-programs";
import {
  masterKinaseAnalysis,
  masterKinaseDemo,
  masterKinaseProfile,
  masterKinaseVerification,
} from "../fixtures/gbm-master-kinases";
import {
  functionalProteotypeAnalysis,
  functionalProteotypeDemo,
  functionalProteotypeProfile,
  functionalProteotypeVerification,
} from "../fixtures/gbm-functional-proteotype";
import {
  gbmRnaPurityAnalysis,
  gbmRnaPurityDemo,
  gbmRnaPurityProfile,
  gbmRnaPurityVerification,
} from "../fixtures/gbm-rna-purity";
import {
  longitudinalAnalysisResult,
  longitudinalDemoRequest,
  longitudinalProfile,
  longitudinalVerification,
} from "../fixtures/longitudinal-gbm";
import {
  phosphoAnalysisResult,
  phosphoDemoRequest,
  phosphoProfile,
  phosphoVerification,
} from "../fixtures/longitudinal-gbm-phospho";
import {
  admittedReactomeTransitionDocuments,
  reactomeTransitionDemoRequest,
} from "../fixtures/longitudinal-gbm-reactome-transition";
import {
  complexTransitionAnalysis,
  complexTransitionDemoRequest,
  complexTransitionProfile,
  complexTransitionVerification,
} from "../fixtures/longitudinal-gbm-complex-transition";
import {
  neftelTransitionAnalysis,
  neftelTransitionDemoRequest,
  neftelTransitionProfile,
  neftelTransitionVerification,
} from "../fixtures/longitudinal-gbm-neftel-transition";
import {
  neftelTransitionProfileDigest,
  neftelTransitionRequestDigest,
} from "../../src/lib/longitudinal-gbm-neftel-transition";
import type { JsonObject } from "../../src/lib/research-state";
import {
  factorGraphAnalysisResult,
  factorGraphDemoRequest,
  factorGraphProfile,
  factorGraphVerification,
} from "../fixtures/gbm-factor-graph";

type WorkbenchMocks = {
  readyStatus?: number;
  ready?: (route: Route) => Promise<void> | void;
  analyze?: (route: Route) => Promise<void> | void;
  demo?: unknown;
};

const demoTopologyProvenance = demoRequest.topology_provenance;
const admittedReactomeTransition = admittedReactomeTransitionDocuments();

function displayNumber(value: number, digits = 3): string {
  return value.toFixed(digits).replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1");
}

async function mockWorkbench(page: Page, options: WorkbenchMocks = {}): Promise<void> {
  const readyStatus = options.readyStatus ?? 200;
  await Promise.all([
    page.route("**/backend/livez", (route) => route.fulfill({ json: { status: "ok" } })),
    page.route("**/backend/readyz", options.ready ?? ((route) => route.fulfill({
      status: readyStatus,
      json: { status: readyStatus === 200 ? "ready" : "degraded" },
    }))),
    page.route("**/backend/v1/research/proteogenomic-state/profile", (route) => route.fulfill({
      json: algorithmProfile,
      headers: { "X-GLIO-Profile-Digest": String(algorithmProfile.profile_digest) },
    })),
    page.route("**/backend/v1/research/proteogenomic-state/demo", (route) => route.fulfill({
      json: options.demo ?? demoRequest,
      headers: {
        "X-GLIO-Profile-Digest": String(algorithmProfile.profile_digest),
        "X-GLIO-Request-Digest": String(analysisResult.request_digest),
      },
    })),
    page.route("**/backend/v1/research/proteogenomic-state/analyze", options.analyze ?? ((route) => route.fulfill({
      json: analysisResult,
      headers: {
        "X-GLIO-Profile-Digest": String(analysisResult.profile_digest),
        "X-GLIO-Request-Digest": String(analysisResult.request_digest),
        "X-GLIO-Result-Digest": String(analysisResult.result_digest),
      },
    }))),
    page.route("**/backend/v1/research/proteogenomic-state/verify", (route) => route.fulfill({
      json: verificationResult,
      headers: {
        "X-GLIO-Profile-Digest": String(algorithmProfile.profile_digest),
        "X-GLIO-Request-Digest": String(verificationResult.recomputed_request_digest),
        "X-GLIO-Result-Digest": String(verificationResult.recomputed_result_digest),
      },
    })),
  ]);
}

async function openLoadedWorkbench(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByLabel("Proteogenomic state request JSON")).toContainText(demoRequest.sample_id);
}

async function mockGbmLane(page: Page, analyze: (route: Route) => Promise<void> | void = (route) => route.fulfill({ json: gbmAnalysisResult })): Promise<void> {
  await Promise.all([
    page.route("**/backend/v1/research/gbm-proteomic-axes/profile", (route) => route.fulfill({ json: gbmAlgorithmProfile })),
    page.route("**/backend/v1/research/gbm-proteomic-axes/demo", (route) => route.fulfill({ json: gbmDemoRequest })),
    page.route("**/backend/v1/research/gbm-proteomic-axes/analyze", analyze),
    page.route("**/backend/v1/research/gbm-proteomic-axes/verify", (route) => route.fulfill({ json: gbmVerificationResult })),
  ]);
}

async function mockNeftelLane(page: Page): Promise<void> {
  await Promise.all([
    page.route("**/backend/v1/research/neftel-protein-programs/profile", (route) => route.fulfill({ json: neftelProfile })),
    page.route("**/backend/v1/research/neftel-protein-programs/demo", (route) => route.fulfill({ json: neftelDemoRequest })),
    page.route("**/backend/v1/research/neftel-protein-programs/analyze", (route) => route.fulfill({ json: neftelAnalysisResult })),
    page.route("**/backend/v1/research/neftel-protein-programs/verify", (route) => route.fulfill({ json: neftelVerification })),
  ]);
}

async function mockMasterKinaseLane(page: Page, analyze: (route: Route) => Promise<void> | void = (route) => route.fulfill({ json: masterKinaseAnalysis })): Promise<void> {
  await Promise.all([
    page.route("**/backend/v1/research/gbm-master-kinases/profile", (route) => route.fulfill({ json: masterKinaseProfile })),
    page.route("**/backend/v1/research/gbm-master-kinases/demo", (route) => route.fulfill({ json: masterKinaseDemo })),
    page.route("**/backend/v1/research/gbm-master-kinases/analyze", analyze),
    page.route("**/backend/v1/research/gbm-master-kinases/verify", (route) => route.fulfill({ json: masterKinaseVerification })),
  ]);
}

async function mockFunctionalProteotypeLane(page: Page): Promise<void> {
  await Promise.all([
    page.route("**/backend/v1/research/gbm-functional-proteotype/profile", (route) => route.fulfill({ json: functionalProteotypeProfile })),
    page.route("**/backend/v1/research/gbm-functional-proteotype/demo", (route) => route.fulfill({ json: functionalProteotypeDemo })),
    page.route("**/backend/v1/research/gbm-functional-proteotype/analyze", (route) => route.fulfill({ json: functionalProteotypeAnalysis })),
    page.route("**/backend/v1/research/gbm-functional-proteotype/verify", (route) => route.fulfill({ json: functionalProteotypeVerification })),
  ]);
}

async function mockGbmRnaPurityLane(
  page: Page,
  analyze: (route: Route) => Promise<void> | void = (route) => route.fulfill({ json: gbmRnaPurityAnalysis }),
): Promise<void> {
  await Promise.all([
    page.route("**/backend/v1/research/gbm-rna-purity/profile", (route) => route.fulfill({ json: gbmRnaPurityProfile })),
    page.route("**/backend/v1/research/gbm-rna-purity/demo", (route) => route.fulfill({ json: gbmRnaPurityDemo })),
    page.route("**/backend/v1/research/gbm-rna-purity/analyze", analyze),
    page.route("**/backend/v1/research/gbm-rna-purity/verify", (route) => route.fulfill({ json: gbmRnaPurityVerification })),
  ]);
}

async function mockLongitudinalLane(page: Page, analyze: (route: Route) => Promise<void> | void = (route) => route.fulfill({ json: longitudinalAnalysisResult })): Promise<void> {
  await Promise.all([
    page.route("**/backend/v1/research/longitudinal-gbm/profile", (route) => route.fulfill({ json: longitudinalProfile })),
    page.route("**/backend/v1/research/longitudinal-gbm/demo", (route) => route.fulfill({ json: longitudinalDemoRequest })),
    page.route("**/backend/v1/research/longitudinal-gbm/analyze", analyze),
    page.route("**/backend/v1/research/longitudinal-gbm/verify", (route) => route.fulfill({ json: longitudinalVerification })),
  ]);
}

async function mockLongitudinalPhosphoLane(page: Page, analyze: (route: Route) => Promise<void> | void = (route) => route.fulfill({ json: phosphoAnalysisResult })): Promise<void> {
  await Promise.all([
    page.route("**/backend/v1/research/longitudinal-gbm-phospho/profile", (route) => route.fulfill({ json: phosphoProfile })),
    page.route("**/backend/v1/research/longitudinal-gbm-phospho/demo", (route) => route.fulfill({ json: phosphoDemoRequest })),
    page.route("**/backend/v1/research/longitudinal-gbm-phospho/analyze", analyze),
    page.route("**/backend/v1/research/longitudinal-gbm-phospho/verify", (route) => route.fulfill({ json: phosphoVerification })),
  ]);
}

async function mockReactomeTransitionLane(
  page: Page,
  analyze: (route: Route) => Promise<void> | void = (route) => route.fulfill({
    json: admittedReactomeTransition.result,
    headers: {
      "X-GLIO-Profile-Digest": String(admittedReactomeTransition.result.profile_digest),
      "X-GLIO-Request-Digest": String(admittedReactomeTransition.result.request_digest),
      "X-GLIO-Result-Digest": String(admittedReactomeTransition.result.result_digest),
    },
  }),
): Promise<void> {
  await Promise.all([
    page.route("**/backend/v1/research/longitudinal-gbm-reactome-transition/profile", (route) => route.fulfill({
      json: admittedReactomeTransition.profile,
      headers: {
        "X-GLIO-Profile-Digest": String(admittedReactomeTransition.profile.profile_digest),
      },
    })),
    page.route("**/backend/v1/research/longitudinal-gbm-reactome-transition/demo", (route) => route.fulfill({
      json: admittedReactomeTransition.request,
      headers: {
        "X-GLIO-Profile-Digest": String(admittedReactomeTransition.profile.profile_digest),
        "X-GLIO-Request-Digest": String(admittedReactomeTransition.profile.demo_request_digest),
      },
    })),
    page.route("**/backend/v1/research/longitudinal-gbm-reactome-transition/analyze", analyze),
    page.route("**/backend/v1/research/longitudinal-gbm-reactome-transition/verify", (route) => route.fulfill({
      json: admittedReactomeTransition.verification,
      headers: {
        "X-GLIO-Profile-Digest": String(admittedReactomeTransition.profile.profile_digest),
        "X-GLIO-Request-Digest": String(admittedReactomeTransition.verification.recomputed_request_digest),
        "X-GLIO-Result-Digest": String(admittedReactomeTransition.verification.recomputed_result_digest),
      },
    })),
  ]);
}

async function mockComplexTransitionLane(
  page: Page,
  analyze: (route: Route) => Promise<void> | void = (route) => route.fulfill({
    json: complexTransitionAnalysis,
    headers: {
      "X-GLIO-Profile-Digest": String(complexTransitionAnalysis.profile_digest),
      "X-GLIO-Request-Digest": String(complexTransitionAnalysis.request_digest),
      "X-GLIO-Result-Digest": String(complexTransitionAnalysis.result_digest),
    },
  }),
): Promise<void> {
  await Promise.all([
    page.route("**/backend/v1/research/longitudinal-gbm-complex-transition/profile", (route) => route.fulfill({
      json: complexTransitionProfile,
      headers: { "X-GLIO-Profile-Digest": String(complexTransitionProfile.profile_digest) },
    })),
    page.route("**/backend/v1/research/longitudinal-gbm-complex-transition/demo", (route) => route.fulfill({ json: complexTransitionDemoRequest })),
    page.route("**/backend/v1/research/longitudinal-gbm-complex-transition/analyze", analyze),
    page.route("**/backend/v1/research/longitudinal-gbm-complex-transition/verify", (route) => route.fulfill({
      json: complexTransitionVerification,
      headers: {
        "X-GLIO-Profile-Digest": String(complexTransitionVerification.authoritative_profile_digest),
        "X-GLIO-Request-Digest": String(complexTransitionVerification.recomputed_request_digest),
        "X-GLIO-Result-Digest": String(complexTransitionVerification.recomputed_result_digest),
      },
    })),
  ]);
}

async function mockNeftelTransitionLane(
  page: Page,
  options: {
    analyze?: (route: Route) => Promise<void> | void;
    demo?: JsonObject;
    demoDigestHeader?: string;
    profile?: JsonObject;
    profileDigestHeader?: string;
  } = {},
): Promise<void> {
  const profile = options.profile ?? neftelTransitionProfile;
  const demo = options.demo ?? neftelTransitionDemoRequest;
  const analyze = options.analyze ?? ((route: Route) => route.fulfill({
    json: neftelTransitionAnalysis,
    headers: {
      "X-GLIO-Profile-Digest": String(neftelTransitionAnalysis.profile_digest),
      "X-GLIO-Request-Digest": String(neftelTransitionAnalysis.request_digest),
      "X-GLIO-Result-Digest": String(neftelTransitionAnalysis.result_digest),
    },
  }));
  await Promise.all([
    page.route("**/backend/v1/research/longitudinal-gbm-neftel-transition/profile", (route) => route.fulfill({
      json: profile,
      headers: {
        "X-GLIO-Profile-Digest": options.profileDigestHeader
          ?? String(profile.profile_digest),
      },
    })),
    page.route("**/backend/v1/research/longitudinal-gbm-neftel-transition/demo", (route) => route.fulfill({
      json: demo,
      headers: {
        "X-GLIO-Request-Digest": options.demoDigestHeader
          ?? neftelTransitionRequestDigest(demo),
      },
    })),
    page.route("**/backend/v1/research/longitudinal-gbm-neftel-transition/analyze", analyze),
    page.route("**/backend/v1/research/longitudinal-gbm-neftel-transition/verify", (route) => route.fulfill({
      json: neftelTransitionVerification,
      headers: {
        "X-GLIO-Profile-Digest": String(neftelTransitionProfile.profile_digest),
        "X-GLIO-Request-Digest": String(neftelTransitionVerification.recomputed_request_digest),
        "X-GLIO-Result-Digest": String(neftelTransitionVerification.recomputed_result_digest),
      },
    })),
  ]);
}

async function mockFactorGraphLane(
  page: Page,
  analyze: (route: Route) => Promise<void> | void = (route) => route.fulfill({
    json: factorGraphAnalysisResult,
    headers: {
      "X-GLIO-Profile-Digest": String(factorGraphAnalysisResult.profile_digest),
      "X-GLIO-Request-Digest": String(factorGraphAnalysisResult.request_digest),
      "X-GLIO-Result-Digest": String(factorGraphAnalysisResult.result_digest),
    },
  }),
): Promise<void> {
  await Promise.all([
    page.route("**/backend/v1/research/gbm-factor-graph/profile", (route) => route.fulfill({
      json: factorGraphProfile,
      headers: { "X-GLIO-Profile-Digest": String(factorGraphProfile.profile_digest) },
    })),
    page.route("**/backend/v1/research/gbm-factor-graph/demo", (route) => route.fulfill({
      json: factorGraphDemoRequest,
      headers: {
        "X-GLIO-Profile-Digest": String(factorGraphProfile.profile_digest),
        "X-GLIO-Request-Digest": String(factorGraphProfile.demo_request_digest),
      },
    })),
    page.route("**/backend/v1/research/gbm-factor-graph/analyze", analyze),
    page.route("**/backend/v1/research/gbm-factor-graph/verify", (route) => route.fulfill({
      json: factorGraphVerification,
      headers: {
        "X-GLIO-Profile-Digest": String(factorGraphProfile.profile_digest),
        "X-GLIO-Request-Digest": String(factorGraphVerification.recomputed_request_digest),
        "X-GLIO-Result-Digest": String(factorGraphVerification.recomputed_result_digest),
      },
    })),
  ]);
}

test("runs the demo and verifies its replay receipt", async ({ page }) => {
  await mockWorkbench(page);
  await openLoadedWorkbench(page);

  await expect(page.getByRole("heading", { name: /Follow the evidence/ })).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await expect(page.getByText(`Sample ${demoRequest.sample_id}`)).toBeVisible();
  await expect(page.getByText("EGFR").first()).toBeVisible();
  await expect(page.getByText("0 full · 56 estimated")).toBeVisible();
  await expect(page.getByText(/Every estimate is capped LIMITED/)).toBeVisible();
  await expect(page.locator(".kinase-table .support-badge.limited")).toHaveCount(1);

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.getByText(/"solver_trace_match": true/)).toBeVisible();
});

test("runs and verifies the published GBM proteomic-axis lane with explicit zero-fill semantics", async ({ page }) => {
  await mockWorkbench(page);
  await mockGbmLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /GBM proteomic axes/ }).click();
  await expect(page.getByLabel("GBM proteomic axes request JSON")).toContainText(gbmDemoRequest.sample_id);
  await expect(page.getByRole("heading", { name: /Resolve glioblastoma programs/ })).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.getByText(`Sample ${gbmDemoRequest.sample_id}`)).toBeVisible();
  await expect(page.locator("[data-signature-id]")).toHaveCount(7);
  await expect(page.getByRole("heading", { name: "Seven proteomic signature scores" })).toBeVisible();
  await expect(page.locator('[data-signature-id="EGFR_UP.V1_UP"]')).toContainText("+0.9182");
  await expect(page.locator('[data-signature-id="SWEET_KRAS_TARGETS_UP"]')).toContainText("2.1%");
  await expect(page.getByText(/not biological absence or suppression/).first()).toBeVisible();

  await page.getByRole("tab", { name: "evidence" }).click();
  await expect(page.getByRole("heading", { name: "Evidence-conserving model input" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Protein evidence ledger" })).toBeVisible();
  await expect(page.getByText("excluded from point prediction")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top summed tree-path drivers" })).toBeVisible();
  await expect(page.getByText("not SHAP · not causal effects")).toBeVisible();

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.locator(".receipt-panel pre")).toContainText('"model_source_match": true');
  await expect(page.getByRole("heading", { name: "GBM model limitations" })).toBeVisible();
});

test("downloads GBM request and result receipts and cancels a stalled model run", async ({ page }) => {
  await mockWorkbench(page);
  await mockGbmLane(page);
  await openLoadedWorkbench(page);
  await page.getByRole("button", { name: /GBM proteomic axes/ }).click();
  await expect(page.getByLabel("GBM proteomic axes request JSON")).toContainText(gbmDemoRequest.sample_id);
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await expect(page.getByText(`Sample ${gbmDemoRequest.sample_id}`)).toBeVisible();

  const requestDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Request" }).click();
  expect((await requestDownload).suggestedFilename()).toBe(`${gbmDemoRequest.sample_id}-request.json`);
  const resultDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Result" }).click();
  expect((await resultDownload).suggestedFilename()).toBe(`${gbmDemoRequest.sample_id}-receipt.json`);

  await page.unroute("**/backend/v1/research/gbm-proteomic-axes/analyze");
  await page.route("**/backend/v1/research/gbm-proteomic-axes/analyze", async () => new Promise<void>(() => undefined));
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(page.getByText("Analysis cancelled. No request or result was persisted.")).toBeVisible();
});

test("runs Neftel exact modules and derived families with q-values, abstention, and replay", async ({ page }) => {
  await mockWorkbench(page);
  await mockNeftelLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /Neftel protein programs/ }).click();
  await expect(page.getByLabel("Neftel protein program request JSON")).toContainText(neftelDemoRequest.sample_id);
  await expect(page.getByRole("heading", { name: /Map glioblastoma programs/ })).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.locator("[data-program-id]")).toHaveCount(13);
  await expect(page.locator('[data-program-id="AC"]')).toContainText("+1.122");
  await expect(page.locator('[data-program-id="AC"]')).toContainText("0.0154");
  await expect(page.locator('[data-program-id="MES1"]')).toContainText("abstained");
  await expect(page.getByText(/not cell fractions/).first()).toBeVisible();

  await page.getByRole("tab", { name: "evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Standardized protein contrast ledger" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Drivers and marker-family ablations" })).toBeVisible();
  await expect(page.getByText("omit AC").first()).toBeVisible();

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Neftel program limitations" })).toBeVisible();
  await expect(page.locator(".receipt-panel pre")).toContainText('"semantic_match": true');
});

test("runs, explains, downloads, verifies, and cancels the 24-signature GBM master-kinase lane", async ({ page }) => {
  await mockWorkbench(page);
  await mockMasterKinaseLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /GBM master kinases/ }).click();
  const editor = page.getByLabel("GBM master kinase request JSON");
  await expect(editor).toContainText(masterKinaseDemo.sample_id);
  await expect(page.getByRole("heading", { name: /Interrogate GBM kinase signatures/ })).toBeVisible();
  await editor.fill(JSON.stringify(masterKinaseDemo, null, 2));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText(/Valid master-kinase request · 4 active phosphosites · 24 pinned signatures/)).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.getByText(`Sample ${masterKinaseDemo.sample_id}`)).toBeVisible();
  await expect(page.locator("[data-master-kinase-id]")).toHaveCount(24);
  await expect(page.locator('[data-master-kinase-subtype="GPM"] [data-master-kinase-id]')).toHaveCount(9);
  await expect(page.locator('[data-master-kinase-subtype="MTC"] [data-master-kinase-id]')).toHaveCount(1);
  await expect(page.locator('[data-master-kinase-subtype="NEU"] [data-master-kinase-id]')).toHaveCount(7);
  await expect(page.locator('[data-master-kinase-subtype="PPR"] [data-master-kinase-id]')).toHaveCount(7);
  await expect(page.locator('[data-master-kinase-id="PRKCD"]')).toContainText("+1.055");
  await expect(page.locator('[data-master-kinase-id="PRKCD"]')).toContainText("0.0336");
  await expect(page.locator('[data-master-subtype-id="MTC"]')).toContainText("limited");
  await expect(page.getByText("published signatures · not an exact SPHINKS port")).toBeVisible();
  await expect(page.getByText("omit S").first()).toBeVisible();

  const requestDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Request" }).click();
  expect((await requestDownload).suggestedFilename()).toBe(`${masterKinaseDemo.sample_id}-request.json`);
  const resultDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Result" }).click();
  expect((await resultDownload).suggestedFilename()).toBe(`${masterKinaseDemo.sample_id}-receipt.json`);

  await page.getByRole("tab", { name: "evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Independent master-kinase concordance evidence" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Phosphosite contrast ledger" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Phosphosite drivers and edge-family ablations" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Pinned source provenance" })).toBeVisible();

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Master-kinase concordance limitations" })).toBeVisible();
  await expect(page.locator(".receipt-panel pre")).toContainText('"semantic_match": true');

  await page.unroute("**/backend/v1/research/gbm-master-kinases/analyze");
  await page.route("**/backend/v1/research/gbm-master-kinases/analyze", async () => new Promise<void>(() => undefined));
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(page.getByText("Analysis cancelled. No request or result was persisted.")).toBeVisible();
});

test("runs and verifies four-axis functional-proteotype concordance without a subtype or sample-pathway claim", async ({ page }) => {
  await mockWorkbench(page);
  await mockFunctionalProteotypeLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /GBM functional proteotype/ }).click();
  const editor = page.getByLabel("GBM functional proteotype request JSON");
  await expect(editor).toContainText(functionalProteotypeDemo.sample_id);
  await expect(page.getByRole("heading", { name: /Resolve four GBM source axes/ })).toBeVisible();
  await expect(page.getByText(/not patient subtype labels, probabilities, winners/)).toBeVisible();
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText(/Valid functional-proteotype request · 100 active proteins · 4 constrained source axes/)).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.getByText(`Sample ${functionalProteotypeDemo.sample_id}`)).toBeVisible();
  await expect(page.locator("[data-functional-axis-id]")).toHaveCount(4);
  await expect(page.locator('[data-functional-axis-id="GPM"]')).toContainText("+1.235");
  await expect(page.locator('[data-functional-axis-id="GPM"]')).toContainText("0.0078");
  await expect(page.getByRole("heading", { name: "Four constrained source-axis coordinates" })).toBeVisible();
  await expect(
    page.locator(".result-panel .boundary-chip").filter({ hasText: "not subtype probabilities" }),
  ).toContainText("Σ z = 0");
  await expect(page.getByRole("heading", { name: "Top drivers and evidence-conserving ablations" })).toBeVisible();
  await expect(page.getByText("omit source rank quartile · source_rank_quartile:1").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Source-cohort pathway context" })).toBeVisible();
  await expect(page.getByText("sample inference: not evaluated")).toBeVisible();

  await page.getByRole("tab", { name: "evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Evidence-conserving protein input" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Standardized protein contrast ledger" })).toBeVisible();
  await expect(page.getByText("Subtype calls emitted")).toBeVisible();
  await expect(page.getByText("No sample pathway scoring")).toBeVisible();

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Functional-proteotype limitations" })).toBeVisible();
  await expect(page.locator(".receipt-panel pre")).toContainText('"solver_trace_match": true');
  await expect(page.locator(".limitations-panel")).toContainText("sample pathway inference is not evaluated");
});

test("validates, explains, downloads, and verifies the exact published GBMPurity lane", async ({ page }) => {
  await mockWorkbench(page);
  await mockGbmRnaPurityLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /GBM RNA purity/ }).click();
  const editor = page.getByLabel("GBM RNA purity request JSON");
  await expect(editor).toContainText(gbmRnaPurityDemo.sample_id);
  await expect(page.getByRole("heading", { name: /Estimate malignant-cell fraction/ })).toBeVisible();

  await editor.fill(JSON.stringify({
    ...gbmRnaPurityDemo,
    context: { ...gbmRnaPurityDemo.context, disease_context: "recurrent_glioma" },
  }));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.locator(".studio-message[role=alert]")).toContainText(
    'context.disease_context must equal "primary_IDH_wildtype_glioblastoma".',
  );

  await editor.fill(JSON.stringify(gbmRnaPurityDemo));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText("Valid GBMPurity request · 5,829 unique raw-count genes · 5,829 nonzero.")).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.getByText(`Sample ${gbmRnaPurityDemo.sample_id}`)).toBeVisible();
  await expect(page.locator(".summary-grid").filter({ hasText: "ESTIMATED MALIGNANT FRACTION" })).toContainText("13.2%");
  await expect(page.getByRole("heading", { name: "Source-model coverage and zero-fill burden" })).toBeVisible();
  const coverage = page.locator(".zero-fill-panel").filter({ hasText: "Recognized model genes" }).first();
  await expect(coverage).toContainText("5,829");
  await expect(coverage.getByText("Missing / zero-filled", { exact: true }).locator("..")).toContainText("0");
  await expect(page.getByRole("heading", { name: "Network activation trace" })).toBeVisible();
  await expect(page.getByText("10 / 32", { exact: true })).toBeVisible();
  await expect(page.getByText("5 / 16", { exact: true })).toBeVisible();
  const localDriver = page.locator('[data-purity-attribution-gene="NOSTRIN"]');
  await expect(localDriver).toContainText("-0.009518");
  await expect(localDriver).toContainText("lowers raw estimate");
  await expect(page.getByRole("heading", { name: "No fabricated calibrated interval" })).toBeVisible();
  await expect(page.getByText(/one fitted MLP and no calibrated ensemble/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "GBMPurity provenance" })).toBeVisible();
  await expect(page.getByText("https://github.com/scmpht/GBMPurity", { exact: true })).toBeVisible();
  await expect(page.getByText(/commit af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950/)).toBeVisible();

  const requestDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Request" }).click();
  expect((await requestDownload).suggestedFilename()).toBe(`${gbmRnaPurityDemo.sample_id}-request.json`);
  const resultDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Result" }).click();
  expect((await resultDownload).suggestedFilename()).toBe(`${gbmRnaPurityDemo.sample_id}-receipt.json`);

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.locator(".receipt-panel pre")).toContainText('"semantic_match": true');
  const provenanceReceipt = page.locator(".json-panel").filter({
    has: page.getByRole("heading", { name: "Model provenance" }),
  }).locator("pre");
  await expect(provenanceReceipt).toContainText('"converted_artifact_file_sha256"');
  await expect(provenanceReceipt).toContainText("2999d845c602c7b8b44d45c37a7f43bea57ad6a930af12f9c7b56cc221ffccc2");
  await expect(provenanceReceipt).toContainText("8a2e26d736fb8e1eb2a0ddf5799e2368acb1b6798275d75ef9c60f0c49204112");
  await expect(provenanceReceipt).toContainText("2d9ceef433761d9b68419bce4c9c7ed4fb1009b9b195f1b1ea2d81f8913a30f4");
});

test("cancels a stalled GBMPurity forward pass without producing a receipt", async ({ page }) => {
  await mockWorkbench(page);
  await mockGbmRnaPurityLane(page, async () => new Promise<void>(() => undefined));
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /GBM RNA purity/ }).click();
  await expect(page.getByLabel("GBM RNA purity request JSON")).toContainText(gbmRnaPurityDemo.sample_id);
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await page.getByRole("button", { name: "Cancel run" }).click();

  await expect(page.getByText("Analysis cancelled. No request or result was persisted.")).toBeVisible();
  await expect(page.getByText("Awaiting analysis")).toBeVisible();
});

test("runs, explains, downloads, verifies, and cancels the longitudinal GBM lane", async ({ page }) => {
  await mockWorkbench(page);
  await mockLongitudinalLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /Longitudinal GBM/ }).click();
  const editor = page.getByLabel("Longitudinal GBM request JSON");
  await expect(editor).toContainText(longitudinalDemoRequest.series_id);
  await expect(page.getByRole("heading", { name: /Trace protein transitions/ })).toBeVisible();
  await editor.fill(JSON.stringify({
    ...longitudinalDemoRequest,
    assay_compatibility: { ...longitudinalDemoRequest.assay_compatibility, log_base: 10 },
  }, null, 2));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.locator(".studio-message[role=alert]")).toContainText("assay_compatibility.log_base must exactly equal 2");
  await editor.fill(JSON.stringify(longitudinalDemoRequest, null, 2));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText("Valid longitudinal GBM request · 4 ordered time points · 16 active protein observations.")).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.getByText(`Series ${longitudinalDemoRequest.series_id}`)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Longitudinal concordance timeline" })).toBeVisible();
  await expect(page.locator("[data-time-point-id]")).toHaveCount(4);
  await expect(page.locator("[data-longitudinal-transition-id]")).toHaveCount(3);
  await expect(page.locator('[data-longitudinal-transition-id="transition.0"]')).toContainText("+0.932");
  await expect(page.locator('[data-longitudinal-transition-id="transition.0"]')).toContainText("[0.812, 1.052]");
  await expect(page.locator('[data-longitudinal-transition-id="transition.0"]')).toContainText("limited");
  await expect(page.locator('[data-longitudinal-transition-id="transition.0"]')).toContainText("fewer than 64 estimable bootstrap projections");
  await expect(page.locator('[data-longitudinal-transition-id="transition.1"]')).toContainText("reverse aligned");
  await expect(page.getByRole("heading", { name: "Measurement × coefficient covariance" })).toBeVisible();
  await expect(page.locator('[data-uncertainty-interaction-id="transition.0"]')).toContainText("paired bootstrap covariance identity v1");
  await expect(page.locator('[data-uncertainty-interaction-id="transition.0"]')).toContainText("-0.001");
  await expect(page.locator('[data-ablation-kind="source_processing"]').first()).toContainText("ordinary Log");
  await expect(page.locator('[data-ablation-kind="top_driver"]').first()).toContainText("omit EGFR");
  await expect(page.locator("[data-pelt-boundary]")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Exact transition-rate Huber PELT" })).toBeVisible();
  await expect(page.getByText(/fewer than 64 joint bootstrap rate paths for full support/)).toBeVisible();
  await expect(page.getByText(/rates per 90 days before segmentation/)).toBeVisible();

  const requestDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Request" }).click();
  expect((await requestDownload).suggestedFilename()).toBe(`${longitudinalDemoRequest.series_id}-request.json`);
  const resultDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Result" }).click();
  expect((await resultDownload).suggestedFilename()).toBe(`${longitudinalDemoRequest.series_id}-receipt.json`);

  await page.getByRole("tab", { name: "evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Protein-level source-cohort transition evidence" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ordered protein evidence ledger" })).toBeVisible();
  await expect(page.getByText("not patient evolution or recurrence prediction")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Assay and quantification attestation" })).toBeVisible();
  await expect(page.locator(".json-panel").filter({ hasText: "Assay and quantification attestation" })).toContainText("tmt11_plexed_mass_spectrometry");
  await expect(page.locator(".json-panel").filter({ hasText: "Assay and quantification attestation" })).toContainText("unshared_peptide_protein_abundance_ratio");
  await expect(page.getByRole("heading", { name: "Model provenance" })).toBeVisible();

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Longitudinal GBM limitations" })).toBeVisible();
  await expect(page.locator(".receipt-panel pre")).toContainText('"transition_semantic_match": true');
  await expect(page.locator(".receipt-panel pre")).toContainText('"pelt_semantic_match": true');

  await page.unroute("**/backend/v1/research/longitudinal-gbm/analyze");
  await page.route("**/backend/v1/research/longitudinal-gbm/analyze", async () => new Promise<void>(() => undefined));
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(page.getByText("Analysis cancelled. No request or result was persisted.")).toBeVisible();
});

test("runs, audits, verifies, downloads, and cancels the KNCC Reactome conditional-transition lane", async ({ page }) => {
  await mockWorkbench(page);
  await mockReactomeTransitionLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /GBM Reactome transitions/ }).click();
  const editor = page.getByLabel("Longitudinal GBM Reactome transition request JSON");
  await expect(editor).toContainText(reactomeTransitionDemoRequest.series_id);
  await expect(page.getByRole("heading", { name: /Condition GBM transitions/ })).toBeVisible();
  await expect(page.locator(".probe-badge").filter({ hasText: "LIVE" })).toContainText("online");
  await expect(page.locator(".probe-badge").filter({ hasText: "READY" })).toContainText("online");
  await expect(page.getByRole("link", { name: "API console" })).toHaveAttribute("href", "/api-console");

  await editor.fill(JSON.stringify({
    ...reactomeTransitionDemoRequest,
    profile_id: "latest",
  }, null, 2));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.locator(".studio-message[role=alert]")).toContainText("profile_id must equal kncc-reactome-conditional-transition/1.0.0");
  await editor.fill(JSON.stringify(reactomeTransitionDemoRequest, null, 2));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText("Valid Reactome transition request · 2 ordered time points · 12 active protein observations · 10 fixed pathways.")).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.getByText(`Series ${reactomeTransitionDemoRequest.series_id}`)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ten-pathway conditional transition interval matrix" })).toBeVisible();
  await expect(page.locator("[data-reactome-pathway-row]")).toHaveCount(10);
  await expect(page.locator("[data-reactome-matrix-cell]")).toHaveCount(10);
  const pi3k = page.locator('[data-reactome-pathway-row="R-HSA-198203"]');
  await expect(pi3k).toContainText("PI3K/AKT activation");
  await expect(pi3k).toContainText("LIMITED · 0 unique fitted members");
  await expect(page.getByText(/displayed number is only a conditional source-cohort concordance coordinate/)).toBeVisible();
  await expect(page.locator('[data-reactome-coordinate="R-HSA-177929"]')).toContainText("improved 4 of 5 evaluable (five planned)");
  await expect(page.locator('[data-reactome-coordinate="R-HSA-186797"]')).toContainText("improved 2 of 3 evaluable (five planned)");
  await expect(page.getByRole("heading", { name: "Coverage, censoring, and measurement × fitted-model sensitivity" })).toBeVisible();
  await expect(page.locator('[data-reactome-coverage="R-HSA-198203"]')).toContainText("0 / 0%");
  await expect(page.getByRole("heading", { name: "Top conditional contributions" })).toBeVisible();
  await expect(page.getByText("local numerical terms · never causal drivers")).toBeVisible();
  await expect(page.locator('[data-reactome-contributions="R-HSA-177929"]')).toContainText("EGFR");
  await expect(page.getByRole("heading", { name: "Conditional-coordinate sensitivity ledger" })).toBeVisible();
  await expect(page.locator('[data-reactome-ablation-kind="source_processing"]').first()).toContainText("source-processing sensitivity");
  await expect(page.locator('[data-reactome-ablation-kind="degree_normalization"]').first()).toContainText("topology / degree normalization");
  await expect(page.locator('[data-reactome-ablation-kind="unique_members"]').first()).toContainText("unique-member attribution");
  await expect(page.locator('[data-reactome-ablation-kind="leave_pathway_out"]').first()).toContainText("leave-pathway-out");
  await expect(page.locator('[data-reactome-ablation-kind="overlapping_pathway"]').first()).toContainText("overlap removal");
  await expect(page.locator('[data-reactome-ablation-kind="top_contribution"]').first()).toContainText("measurement / top-contribution omission");
  await expect(page.getByRole("heading", { name: "Evidence ceiling and reconstruction audit" })).toBeVisible();
  await expect(page.getByText("not external validation", { exact: true })).toBeVisible();
  await expect(page.getByText("all 10 cross zero")).toBeVisible();

  const requestDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Request" }).click();
  expect((await requestDownload).suggestedFilename()).toBe(`${reactomeTransitionDemoRequest.series_id}-request.json`);
  const resultDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Result" }).click();
  expect((await resultDownload).suggestedFilename()).toBe(`${reactomeTransitionDemoRequest.series_id}-receipt.json`);

  await page.getByRole("tab", { name: "evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "KNCC protein-transition evidence on a locked Reactome panel" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ordered protein evidence ledger" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Reactome V97 and KNCC provenance" })).toBeVisible();
  await expect(page.getByText("not pathway activity, flux, or clinical prediction")).toBeVisible();

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Reactome transition limitations" })).toBeVisible();
  await expect(page.locator(".receipt-panel pre")).toContainText('"pathway_semantic_match": true');
  await expect(page.locator(".receipt-panel pre")).toContainText('"ablation_semantic_match": true');

  await page.unroute("**/backend/v1/research/longitudinal-gbm-reactome-transition/analyze");
  await page.route("**/backend/v1/research/longitudinal-gbm-reactome-transition/analyze", async () => new Promise<void>(() => undefined));
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(page.getByText("Analysis cancelled. No request or result was persisted.")).toBeVisible();
});

test("runs, explains, downloads, and replays all 28 fitted Reactome participant sets", async ({ page }) => {
  test.setTimeout(60_000);
  await mockWorkbench(page);
  await mockComplexTransitionLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /GBM complex transitions/ }).click();
  const editor = page.getByLabel("Longitudinal GBM complex transition request JSON");
  await expect(editor).toContainText(complexTransitionDemoRequest.series_id);
  await expect(page.getByRole("heading", { name: /Resolve GBM participant sets/ })).toBeVisible();
  await expect(page.getByText(/Do not invent complex activity/)).toBeVisible();

  await editor.fill(JSON.stringify({ ...complexTransitionDemoRequest, profile_id: "latest" }, null, 2));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.locator(".studio-message[role=alert]")).toContainText(
    "profile_id must equal kncc-reactome-complex-transition/1.0.0",
  );
  await editor.fill(JSON.stringify(complexTransitionDemoRequest, null, 2));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText(
    "Valid Reactome complex-transition request · 3 ordered time points · 360 active protein observations · 28 fixed participant sets.",
  )).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.getByText(`Series ${complexTransitionDemoRequest.series_id}`)).toBeVisible();
  const complexTable = page.locator("section.result-panel").filter({
    has: page.getByRole("heading", { name: "Robust member-transition coordinates" }),
  });
  await expect(complexTable.locator("tbody tr")).toHaveCount(56);
  await expect(complexTable).toContainText("R-HSA-179791");
  await expect(complexTable).toContainText("mTORC1");
  await expect(page.getByRole("heading", { name: "Numerical drivers and ablations" })).toBeVisible();
  await expect(page.getByText("local decomposition · never causal drivers")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Fitted participant-set evidence ceiling" })).toBeVisible();
  await expect(page.getByText("14,988 held-member evaluations.")).toBeVisible();
  await expect(page.getByText("same cohort · not external validation", { exact: true })).toBeVisible();

  const requestDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Request" }).click();
  expect((await requestDownload).suggestedFilename()).toBe(`${complexTransitionDemoRequest.series_id}-request.json`);
  const resultDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Result" }).click();
  expect((await resultDownload).suggestedFilename()).toBe(`${complexTransitionDemoRequest.series_id}-receipt.json`);

  await page.getByRole("tab", { name: "evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "KNCC protein transitions on exact Reactome participant sets" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Complex-coordinate uncertainty ledger" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "PDC000514, Reactome V97, and fitted-factor provenance" })).toBeVisible();
  await expect(page.getByText("aggregate model · no patient-level rows packaged")).toBeVisible();

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Complex-transition limitations" })).toBeVisible();
  await expect(page.locator(".receipt-panel pre")).toContainText('"complex_semantic_match": true');
  await expect(page.locator(".receipt-panel pre")).toContainText('"ablation_semantic_match": true');

  await page.unroute("**/backend/v1/research/longitudinal-gbm-complex-transition/analyze");
  await page.route("**/backend/v1/research/longitudinal-gbm-complex-transition/analyze", async () => new Promise<void>(() => undefined));
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(page.getByText("Analysis cancelled. No request or result was persisted.")).toBeVisible();
});

test("runs, explains, and replays the eight exact LIMITED Neftel transition programs", async ({ page }) => {
  test.setTimeout(60_000);
  await mockWorkbench(page);
  await mockNeftelTransitionLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /GBM Neftel transitions/ }).click();
  const editor = page.getByLabel("Longitudinal GBM Neftel program transition request JSON");
  await expect(editor).toContainText(neftelTransitionDemoRequest.series_id);
  await expect(page.getByRole("heading", { name: /Track bulk-protein program coordinates/ })).toBeVisible();
  await expect(page.getByText("LIMITED · loses to equal membership", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText(
    "Valid Neftel program-transition request · 4 ordered time points · 1024 active protein observations · 8 exact programs · LIMITED fitted dictionary.",
  )).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.getByText(`Series ${neftelTransitionDemoRequest.series_id}`)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Eight-program conditional transition interval matrix" })).toBeVisible();
  await expect(page.locator("[data-neftel-program-row]")).toHaveCount(8);
  await expect(page.locator("[data-neftel-matrix-cell]")).toHaveCount(24);
  await expect(page.locator('[data-neftel-program-row="MES2"]')).toContainText("exact Neftel Table S2 module");
  await expect(page.locator('[data-neftel-program-row="G2/M"]')).toContainText("LIMITED · no individual fitted effect established");
  await expect(page.getByRole("heading", { name: "Coordinate decomposition and request reconstruction" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top conditional contributions" })).toBeVisible();
  await expect(page.locator('[data-neftel-contributions="MES2"]').first()).toContainText("RPL21");
  await expect(page.getByRole("heading", { name: "Conditional-coordinate sensitivity ledger" })).toBeVisible();
  await expect(page.locator('[data-neftel-ablation-kind="global_axis"]').first()).toContainText("global-axis removal");
  await expect(page.locator('[data-neftel-ablation-kind="unique_members"]').first()).toContainText("unique-member attribution");
  await expect(page.getByRole("heading", { name: "Evidence ceiling and reconstruction audit" })).toBeVisible();
  await expect(page.getByText("Release gate failed against equal membership", { exact: true })).toBeVisible();
  await expect(page.getByText("0 individually supported · equal-baseline interval supports positive gain: no", { exact: false })).toBeVisible();

  const requestDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Request" }).click();
  expect((await requestDownload).suggestedFilename()).toBe(`${neftelTransitionDemoRequest.series_id}-request.json`);
  const resultDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Result" }).click();
  expect((await resultDownload).suggestedFilename()).toBe(`${neftelTransitionDemoRequest.series_id}-receipt.json`);

  await page.getByRole("tab", { name: "evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "KNCC protein-transition evidence on a locked Neftel panel" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ordered protein evidence ledger" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Neftel Table S2, HGNC, and KNCC provenance" })).toBeVisible();
  await expect(page.getByText("conditional concordance · not program activity, flux, or clinical prediction", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Neftel transition limitations" })).toBeVisible();
  await expect(page.locator(".receipt-panel pre")).toContainText('"program_semantic_match": true');
  await expect(page.locator(".receipt-panel pre")).toContainText('"ablation_semantic_match": true');

  await page.unroute("**/backend/v1/research/longitudinal-gbm-neftel-transition/analyze");
  await page.route("**/backend/v1/research/longitudinal-gbm-neftel-transition/analyze", async () => new Promise<void>(() => undefined));
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(page.getByText("Analysis cancelled. No request or result was persisted.")).toBeVisible();
});

test("rejects a valid but non-canonical Neftel transition demo before editor admission", async ({ page }) => {
  const nonDemoRequest: JsonObject = {
    ...neftelTransitionDemoRequest,
    series_id: "synthetic.kncc-neftel.non-demo",
  };
  await mockWorkbench(page);
  await mockNeftelTransitionLane(page, { demo: nonDemoRequest });
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /GBM Neftel transitions/ }).click();
  const editor = page.getByLabel("Longitudinal GBM Neftel program transition request JSON");
  await expect(editor).toHaveValue("{}");
  await expect(page.locator(".studio-message[role=alert]")).toContainText(
    "The canonical demo request digest must match the loaded profile.demo_request_digest.",
  );
  await expect(editor).not.toContainText("synthetic.kncc-neftel.non-demo");
});

test("rejects a Neftel transition demo with a forged request-digest header", async ({ page }) => {
  await mockWorkbench(page);
  await mockNeftelTransitionLane(page, {
    demoDigestHeader: `sha256:${"0".repeat(64)}`,
  });
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /GBM Neftel transitions/ }).click();
  const editor = page.getByLabel("Longitudinal GBM Neftel program transition request JSON");
  await expect(editor).toHaveValue("{}");
  await expect(page.locator(".studio-message[role=alert]")).toContainText(
    "X-GLIO-Request-Digest response header must match the canonical demo request digest.",
  );
});

test("rejects a Neftel transition demo that disagrees with its admitted profile", async ({ page }) => {
  const mismatchedProfile: JsonObject = {
    ...neftelTransitionProfile,
    demo_request_digest: `sha256:${"f".repeat(64)}`,
  };
  mismatchedProfile.profile_digest = neftelTransitionProfileDigest(mismatchedProfile);
  await mockWorkbench(page);
  await mockNeftelTransitionLane(page, { profile: mismatchedProfile });
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /GBM Neftel transitions/ }).click();
  const editor = page.getByLabel("Longitudinal GBM Neftel program transition request JSON");
  await expect(editor).toHaveValue("{}");
  await expect(page.locator(".studio-message[role=alert]")).toContainText(
    "The canonical demo request digest must match the loaded profile.demo_request_digest.",
  );
});

test("fails closed on an elevated Neftel transition receipt and forged digest header", async ({ page }) => {
  await mockWorkbench(page);
  const forged = {
    ...neftelTransitionAnalysis,
    output_semantics: "cell_state_transition",
    clinical_prediction: true,
    transitions: neftelTransitionAnalysis.transitions.map((transition, transitionIndex) => transitionIndex === 0
      ? {
        ...transition,
        global_transition: { ...transition.global_transition, support: "supported" },
        programs: transition.programs.map((program, programIndex) => programIndex === 0
          ? { ...program, support: "supported" }
          : program),
      }
      : transition),
  };
  await mockNeftelTransitionLane(page, {
    analyze: (route) => route.fulfill({
      json: forged,
      headers: {
        "X-GLIO-Profile-Digest": String(forged.profile_digest),
        "X-GLIO-Request-Digest": String(forged.request_digest),
        "X-GLIO-Result-Digest": `sha256:${"0".repeat(64)}`,
      },
    }),
  });
  await openLoadedWorkbench(page);
  await page.getByRole("button", { name: /GBM Neftel transitions/ }).click();
  await page.getByRole("button", { name: /Run analysis/ }).click();
  const alert = page.locator(".studio-message[role=alert]");
  await expect(alert).toContainText("result semantics exceed or differ from the admitted research boundary");
  await expect(alert).toContainText("global_transition.support exceeds the lane-wide LIMITED evidence ceiling");
  await expect(alert).toContainText("programs[0].support exceeds the lane-wide LIMITED evidence ceiling");
  await expect(alert).toContainText("X-GLIO-Result-Digest response header must match the admitted payload");
  await expect(page.getByText(`Series ${neftelTransitionDemoRequest.series_id}`)).toHaveCount(0);
});

test("fails closed on a complex-transition receipt with an elevated claim or forged digest header", async ({ page }) => {
  await mockWorkbench(page);
  const forged = { ...complexTransitionAnalysis, infers_complex_activity: true };
  await mockComplexTransitionLane(page, (route) => route.fulfill({
    json: forged,
    headers: {
      "X-GLIO-Profile-Digest": String(forged.profile_digest),
      "X-GLIO-Request-Digest": String(forged.request_digest),
      "X-GLIO-Result-Digest": `sha256:${"0".repeat(64)}`,
    },
  }));
  await openLoadedWorkbench(page);
  await page.getByRole("button", { name: /GBM complex transitions/ }).click();
  await page.getByRole("button", { name: /Run analysis/ }).click();
  const alert = page.locator(".studio-message[role=alert]");
  await expect(alert).toContainText("result.infers_complex_activity must be false");
  await expect(alert).toContainText("X-GLIO-Result-Digest response header must match the admitted payload");
  await expect(page.getByText(`Series ${complexTransitionDemoRequest.series_id}`)).toHaveCount(0);
});

test("renders and replays the KNCC two-block factor-graph composition without cross-modal coupling", async ({ page }) => {
  await mockWorkbench(page);
  await mockFactorGraphLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /KNCC factor graph/ }).click();
  const editor = page.getByLabel("KNCC GBM factor graph request JSON");
  await expect(editor).toContainText(factorGraphDemoRequest.analysis_id);
  await expect(page.getByRole("heading", { name: /Place both result families/ })).toBeVisible();
  await expect(page.getByText("STRUCTURED JSON · MAX 4 MiB")).toBeVisible();
  await expect(page.getByText(/composition and presentation surface, not an additional fitted model/i)).toBeVisible();
  await expect(page.getByText(/execute deterministically in sequence/i)).toBeVisible();

  await editor.fill(JSON.stringify({
    ...factorGraphDemoRequest,
    relationship: "joint_cross_modal_fusion",
  }, null, 2));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.locator(".studio-message[role=alert]")).toContainText(
    "relationship must equal independent_parallel_source_cohort_concordance_no_cross_modal_fusion",
  );
  await editor.fill(JSON.stringify(factorGraphDemoRequest, null, 2));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText("Valid factor-graph composition · 2 protein points · 4 phosphosite points · 4 independent child transitions · 0 fusion edges.")).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.getByText(`Analysis ${factorGraphDemoRequest.analysis_id}`)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Two independent source-cohort concordance blocks" })).toBeVisible();
  await expect(page.getByText(/semantically independent, are executed deterministically in sequence—not concurrently/i)).toBeVisible();
  await expect(page.getByText("cross-modal fusion").first()).toBeVisible();
  await expect(page.getByText("not performed", { exact: true }).first()).toBeVisible();
  await expect(page.locator("[data-factor-block]")).toHaveCount(2);
  await expect(page.locator("[data-factor-node-id]")).toHaveCount(41);
  await expect(page.locator("[data-factor-edge-id]")).toHaveCount(39);
  await expect(page.locator('[data-computational-role="annotation_only"]')).toHaveCount(39);
  await expect(page.getByText("No edge joins these columns.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Reactome conditional-transition result family" })).toBeVisible();
  await expect(page.locator("[data-reactome-pathway-row]")).toHaveCount(10);
  await expect(page.getByRole("heading", { name: "SPHINKS kinase-transition result family" })).toBeVisible();
  await expect(page.locator("[data-factor-kinase-transition-id]")).toHaveCount(3);
  await expect(page.locator('[data-factor-kinase-transition="kinase-transition-0"]')).toHaveCount(24);
  await expect(page.locator('[data-factor-kinase-signature="GSK3B"]').first()).toContainText("+0.31");
  await expect(page.locator("[data-factor-subtype]")).toHaveCount(12);
  await expect(page.locator('[data-factor-kinase-ablation="omit_composite_source_groups"]').first()).toContainText("omit composite source groups");

  const requestDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Request" }).click();
  expect((await requestDownload).suggestedFilename()).toBe(`${factorGraphDemoRequest.analysis_id}-request.json`);
  const resultDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Result" }).click();
  expect((await resultDownload).suggestedFilename()).toBe(`${factorGraphDemoRequest.analysis_id}-receipt.json`);

  await page.getByRole("tab", { name: "evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Evidence remains assay-specific" })).toBeVisible();
  await expect(page.getByText("no shared feature matrix · no cross-assay normalization")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Reactome input and result provenance" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "SPHINKS input and result provenance" })).toBeVisible();
  await expect(page.locator("[data-factor-kinase-observation]")).toHaveCount(12);
  await expect(page.getByText(/same source cohort · not independent validation/i)).toBeVisible();

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Factor-graph composition limitations" })).toBeVisible();
  await expect(page.locator(".receipt-panel pre")).toContainText('"reactome_child_verified": true');
  await expect(page.locator(".receipt-panel pre")).toContainText('"kinase_child_verified": true');
  await expect(page.locator(".receipt-panel pre")).toContainText('"no_cross_modal_fusion_match": true');

  await page.unroute("**/backend/v1/research/gbm-factor-graph/analyze");
  await page.route("**/backend/v1/research/gbm-factor-graph/analyze", async () => new Promise<void>(() => undefined));
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(page.getByText("Analysis cancelled. No request or result was persisted.")).toBeVisible();
});

test("runs, bounds, explains, verifies, and cancels the PDC000515 phosphosite lane", async ({ page }) => {
  await mockWorkbench(page);
  await mockLongitudinalPhosphoLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /Longitudinal phosphosites/ }).click();
  const editor = page.getByLabel("Longitudinal GBM phosphosite request JSON");
  await expect(editor).toContainText(phosphoDemoRequest.series_id);
  await expect(page.getByRole("heading", { name: /Trace phosphosite transitions/ })).toBeVisible();

  await editor.fill(JSON.stringify({
    ...phosphoDemoRequest,
    assay_compatibility: {
      ...phosphoDemoRequest.assay_compatibility,
      source_artifact_content_digest: `sha256:${"f".repeat(64)}`,
    },
  }, null, 2));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.locator(".studio-message[role=alert]")).toContainText("source_artifact_content_digest must exactly equal");
  await editor.fill(JSON.stringify(phosphoDemoRequest, null, 2));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText("Valid longitudinal phosphosite request · 4 ordered time points · 12 active phosphosite observations.")).toBeVisible();
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.getByText(`Series ${phosphoDemoRequest.series_id}`)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Raw phosphosite concordance timeline" })).toBeVisible();
  await expect(page.locator("[data-phospho-time-point-id]")).toHaveCount(4);
  await expect(page.locator("[data-phospho-transition-id]")).toHaveCount(3);
  await expect(page.locator('[data-phospho-transition-id="transition-0"]')).toContainText("+0.81");
  await expect(page.locator('[data-phospho-transition-id="transition-0"]')).toContainText("[0.69, 0.93]");
  await expect(page.locator('[data-phospho-transition-id="transition-0"]')).toContainText("limited");
  await expect(page.getByRole("heading", { name: "Measurement × coefficient × interaction closure" })).toBeVisible();
  await expect(page.locator('[data-phospho-uncertainty-id="transition-0"]')).toContainText("-0.0002");
  await expect(page.locator('[data-phospho-uncertainty-id="transition-0"]')).toContainText("closure residual");
  await expect(page.getByText("SPHINKS AKT1_S473").first()).toBeVisible();
  await expect(page.getByText("signatures AKT1, MTOR").first()).toBeVisible();
  await expect(page.locator('[data-phospho-censored-bounds="transition-2"]')).toContainText("excluded from point projection");
  await expect(page.locator('[data-phospho-ablation-kind="feature_family"]').first()).toContainText("omit exact sphinks crosswalk sites");

  const requestDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Request" }).click();
  expect((await requestDownload).suggestedFilename()).toBe(`${phosphoDemoRequest.series_id}-request.json`);
  const resultDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ Result" }).click();
  expect((await resultDownload).suggestedFilename()).toBe(`${phosphoDemoRequest.series_id}-receipt.json`);

  await page.getByRole("tab", { name: "evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Raw phosphosite transition only" })).toBeVisible();
  await expect(page.getByText("occupancy like")).toBeVisible();
  await expect(page.getByText("not fitted").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Exact phosphosite evidence ledger" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Phosphoproteome compatibility" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Standalone provenance" })).toBeVisible();
  await expect(page.locator(".json-panel").filter({ hasText: "Standalone provenance" })).toContainText("10.1038/s43018-022-00510-x");

  await page.getByRole("button", { name: "Verify replay" }).click();
  await expect(page.getByText("Replay verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Longitudinal phosphosite limitations" })).toBeVisible();
  await expect(page.locator(".receipt-panel pre")).toContainText('"transition_semantic_match": true');
  await expect(page.locator(".receipt-panel pre")).toContainText('"view_semantic_match": true');

  await page.unroute("**/backend/v1/research/longitudinal-gbm-phospho/analyze");
  await page.route("**/backend/v1/research/longitudinal-gbm-phospho/analyze", async () => new Promise<void>(() => undefined));
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(page.getByText("Analysis cancelled. No request or result was persisted.")).toBeVisible();
});

test("keeps longitudinal execution disabled when backend readiness is degraded", async ({ page }) => {
  await mockWorkbench(page, { readyStatus: 503 });
  await mockLongitudinalLane(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /Longitudinal GBM/ }).click();
  await expect(page.getByLabel("Longitudinal GBM request JSON")).toContainText(longitudinalDemoRequest.series_id);
  await expect(page.locator(".probe-badge").filter({ hasText: "LIVE" })).toContainText("online");
  await expect(page.locator(".probe-badge").filter({ hasText: "READY" })).toContainText("degraded");
  await expect(page.getByRole("button", { name: /Run analysis/ })).toBeDisabled();
});

test("gives longitudinal analysis and replay a 130-second client envelope", async ({ page }) => {
  await page.clock.install();
  await mockWorkbench(page);
  await mockLongitudinalLane(page);
  await openLoadedWorkbench(page);
  await page.getByRole("button", { name: /Longitudinal GBM/ }).click();
  await expect(page.getByLabel("Longitudinal GBM request JSON")).toContainText(longitudinalDemoRequest.series_id);
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await expect(page.getByText(`Series ${longitudinalDemoRequest.series_id}`)).toBeVisible();

  await page.unroute("**/backend/v1/research/longitudinal-gbm/verify");
  await page.route("**/backend/v1/research/longitudinal-gbm/verify", async () => new Promise<void>(() => undefined));
  await page.getByRole("button", { name: "Verify replay" }).click();
  await page.clock.fastForward(30_000);
  await expect(page.getByRole("button", { name: "Cancel verification" })).toBeVisible();
  await page.clock.fastForward(100_000);
  await expect(page.getByText("Replay verification timed out after 130 seconds.")).toBeVisible();

  await page.unroute("**/backend/v1/research/longitudinal-gbm/analyze");
  await page.route("**/backend/v1/research/longitudinal-gbm/analyze", async () => new Promise<void>(() => undefined));
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await page.clock.fastForward(30_000);
  await expect(page.getByRole("button", { name: "Cancel run" })).toBeVisible();
  await page.clock.fastForward(100_000);
  await expect(page.getByText("Analysis timed out after 130 seconds. No request or result was persisted.")).toBeVisible();
});

test("renders local kinase enrichment and non-overriding KINOPHOS agreement", async ({ page }) => {
  await mockWorkbench(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /Run analysis/ }).click();
  await expect(page.getByRole("heading", { name: "Kinase rank enrichment" })).toBeVisible();
  const firstKinase = analysisResult.kinase_states[0];
  await expect(page.getByRole("cell", {
    name: `${displayNumber(firstKinase.rank_statistic)} / ${displayNumber(firstKinase.enrichment_score)}`,
  })).toBeVisible();

  await page.getByRole("tab", { name: "evidence" }).click();
  await expect(page.getByRole("heading", { name: "External KINOPHOS agreement" })).toBeVisible();
  const comparison = page.locator("pre").filter({ hasText: "kinophos.synthetic.v1" });
  await expect(comparison).toContainText('"profile_id": "kinophos.synthetic.v1"');
  await expect(comparison).toContainText('"direction_agreement": true');
  await expect(comparison).toContainText("never merged or substituted");
});

test("shows scoped public topology provenance for the executed synthetic demo", async ({ page }) => {
  await mockWorkbench(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /Run analysis/ }).click();
  await page.getByRole("tab", { name: "evidence" }).click();

  await expect(page.getByRole("heading", { name: "Topology provenance" })).toBeVisible();
  await expect(page.getByText("synthetic abstraction", { exact: true })).toBeVisible();
  await expect(page.getByText("Synthetic abstraction declaration", { exact: true })).toBeVisible();
  await expect(page.locator(".topology-panel")).toContainText("repository-native synthetic demo choices");
  const source = page.locator('[data-topology-source-id="reactome.R-HSA-177929.release97"]');
  await expect(source).toContainText("Reactome · release 97");
  await expect(source).toContainText("Signaling by EGFR");
  await expect(source).toContainText("R-HSA-177929");
  await expect(source).toContainText("pathway.RTK.signaling");
  await expect(source).toContainText("sha256:8bfd16fd5aa56ac37ff1d3e8e1bc8a14f27d5ca9cf4204bcfc2231e004823260");
  const sourceLink = source.getByRole("link", { name: /reactome.org\/ContentService/ });
  await expect(sourceLink).toHaveAttribute("target", "_blank");
  await expect(sourceLink).toHaveAttribute("rel", "noopener noreferrer");
  await expect(source.getByRole("link", { name: /CC0-1.0/ })).toHaveAttribute("href", "https://creativecommons.org/publicdomain/zero/1.0/");
});

test("keeps receipt evidence bound to the executed request after editor changes", async ({ page }) => {
  await mockWorkbench(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /Run analysis/ }).click();
  await expect(page.getByText(`Sample ${demoRequest.sample_id}`)).toBeVisible();
  const executedObservation = demoRequest.observations[0];
  const edited = {
    ...demoRequest,
    observations: demoRequest.observations.map((observation, index) => index === 0
      ? { ...observation, observation_id: "obs.edited" }
      : observation),
  };
  await page.getByLabel("Proteogenomic state request JSON").fill(JSON.stringify(edited));
  await page.getByRole("tab", { name: "evidence" }).click();

  await expect(page.getByRole("cell", { name: executedObservation.observation_id })).toBeVisible();
  await expect(page.getByRole("cell", { name: "obs.edited" })).toHaveCount(0);
});

test("renders the executed graph with exact typed nodes and signed directed relations", async ({ page }) => {
  await mockWorkbench(page);
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /Run analysis/ }).click();
  const executedEdge = demoRequest.edges.find((edge) => edge.kind === "kinase_substrate" && edge.sign === -1);
  if (!executedEdge) throw new Error("The locked demo must include a negative kinase-substrate relation.");
  const edited = {
    ...demoRequest,
    edges: demoRequest.edges.filter((edge) => edge.edge_id !== executedEdge.edge_id),
  };
  await page.getByLabel("Proteogenomic state request JSON").fill(JSON.stringify(edited));
  await page.getByRole("tab", { name: "network" }).click();

  const kinase = page.locator(`[data-node-id="${executedEdge.source_id}"]`);
  await expect(kinase).toHaveAttribute("data-node-kind", "kinase");
  await expect(kinase).toHaveAccessibleName(/kinase node/);
  await expect(page.locator('[data-node-kind-column="phosphosite"]')).toContainText("phosphosite");

  const edge = page.locator(`.network-edge[data-edge-id="${executedEdge.edge_id}"]`);
  await expect(edge).toHaveAttribute("data-source-id", executedEdge.source_id);
  await expect(edge).toHaveAttribute("data-target-id", executedEdge.target_id);
  await expect(edge).toHaveAttribute("data-edge-kind", executedEdge.kind);
  await expect(edge).toHaveAttribute("data-edge-sign", String(executedEdge.sign));
  await expect(edge).toHaveAttribute("data-edge-weight", String(executedEdge.weight));
  await expect(edge.locator("path")).toHaveAttribute("marker-end", "url(#network-arrow-negative)");

  const relation = page.locator(`tr[data-relation-id="${executedEdge.edge_id}"]`);
  await expect(relation).toContainText(executedEdge.source_id);
  await expect(relation).toContainText(executedEdge.target_id);
  await expect(relation).toContainText(executedEdge.kind);
  await expect(relation).toContainText("−1 negative");
});

test("cancels an in-flight analysis without producing a result", async ({ page }) => {
  await mockWorkbench(page, { analyze: async () => new Promise<void>(() => undefined) });
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /Run analysis/ }).click();
  const cancel = page.getByRole("button", { name: "Cancel run" });
  await expect(cancel).toBeVisible();
  await cancel.click();

  await expect(page.getByText("Analysis cancelled. No request or result was persisted.")).toBeVisible();
  await expect(page.getByText("Awaiting analysis")).toBeVisible();
});

test("times out a stalled analysis and reports the transport outcome", async ({ page }) => {
  await page.clock.install();
  await mockWorkbench(page, { analyze: async () => new Promise<void>(() => undefined) });
  await openLoadedWorkbench(page);

  await page.getByRole("button", { name: /Run analysis/ }).click();
  await expect(page.getByRole("button", { name: "Cancel run" })).toBeVisible();
  await page.clock.fastForward(30_000);

  await expect(page.getByText("Analysis timed out after 30 seconds. No request or result was persisted.")).toBeVisible();
  await expect(page.getByText("Awaiting analysis")).toBeVisible();
});

test("rejects a malformed graph before calling analyze", async ({ page }) => {
  let analyzeCalls = 0;
  await mockWorkbench(page, {
    analyze: (route) => {
      analyzeCalls += 1;
      return route.fulfill({ json: analysisResult });
    },
  });
  await openLoadedWorkbench(page);

  const malformed = { ...demoRequest, nodes: [demoRequest.nodes[0], demoRequest.nodes[0]] };
  await page.getByLabel("Proteogenomic state request JSON").fill(JSON.stringify(malformed));
  await page.getByRole("button", { name: /Run analysis/ }).click();

  await expect(page.locator(".studio-message[role=alert]")).toContainText("Duplicate node identifiers: protein.EGFR.");
  expect(analyzeCalls).toBe(0);
});

test("blocks typed, semantic, evidence, bound, and KINOPHOS violations before analyze", async ({ page }) => {
  let analyzeCalls = 0;
  await mockWorkbench(page, {
    analyze: (route) => {
      analyzeCalls += 1;
      return route.fulfill({ json: analysisResult });
    },
  });
  await openLoadedWorkbench(page);

  const malformedCases: Array<{ request: unknown; expected: string }> = [
    {
      request: { ...demoRequest, nodes: [{ ...demoRequest.nodes[0], kind: "gene" }] },
      expected: "nodes[0].kind must be one of",
    },
    {
      request: {
        ...demoRequest,
        edges: [{
          edge_id: "edge.invalid-participation",
          source_id: "protein.EGFR",
          target_id: "protein.PTEN",
          kind: "participates_in",
          sign: 1,
          weight: 1,
          essential: false,
        }],
      },
      expected: "participates_in must target a pathway",
    },
    {
      request: { ...demoRequest, observations: [{ ...demoRequest.observations[0], state: "missing" }] },
      expected: "missing/unsupported evidence cannot carry numeric effects",
    },
    {
      request: { ...demoRequest, bootstrap_replicates: 7, permutation_replicates: 2049 },
      expected: "bootstrap_replicates must be an integer from 8 through 256",
    },
    {
      request: {
        ...demoRequest,
        external_kinase_profile: {
          ...demoRequest.external_kinase_profile,
          estimates: [{
            ...demoRequest.external_kinase_profile.estimates[0],
            kinase_id: "protein.EGFR",
            lower_bound: 1,
          }],
        },
      },
      expected: "kinase_id must exactly match a kinase node ID",
    },
    {
      request: {
        ...demoRequest,
        topology_provenance: {
          ...demoTopologyProvenance,
          sources: [{ ...demoTopologyProvenance.sources[0], source_uri: "http://example.org/context.sbml" }],
        },
      },
      expected: "source_uri must be an HTTPS URL",
    },
  ];

  for (const malformed of malformedCases) {
    await page.getByLabel("Proteogenomic state request JSON").fill(JSON.stringify(malformed.request));
    await page.getByRole("button", { name: /Run analysis/ }).click();
    await expect(page.locator(".studio-message[role=alert]")).toContainText(malformed.expected);
  }
  const duplicateKeySource = JSON.stringify(demoRequest).replace(
    '"sample_id":',
    '"sample_id":"forged-sample","sample_id":',
  );
  await page.getByLabel("Proteogenomic state request JSON").fill(duplicateKeySource);
  await page.getByRole("button", { name: /Run analysis/ }).click();
  await expect(page.locator(".studio-message[role=alert]")).toContainText(
    "Duplicate JSON key request.sample_id.",
  );
  expect(analyzeCalls).toBe(0);
});

test("shows degraded readiness independently from liveness", async ({ page }) => {
  await mockWorkbench(page, { readyStatus: 503 });
  await openLoadedWorkbench(page);

  await expect(page.locator(".probe-badge").filter({ hasText: "LIVE" })).toContainText("online");
  await expect(page.locator(".probe-badge").filter({ hasText: "READY" })).toContainText("degraded");
  await expect(page.getByRole("button", { name: /Run analysis/ })).toBeDisabled();
});

test("keeps Run disabled while readiness is checking, then enables it online", async ({ page }) => {
  let delayedReady: Route | null = null;
  await mockWorkbench(page, { ready: (route) => { delayedReady = route; } });
  await openLoadedWorkbench(page);

  const run = page.getByRole("button", { name: /Run analysis/ });
  await expect(run).toBeDisabled();
  await expect(run).toHaveAttribute("title", "Backend readiness must be online to run.");
  await expect.poll(() => delayedReady !== null).toBe(true);
  const capturedReady = delayedReady as Route | null;
  if (!capturedReady) throw new Error("The readiness request was not captured.");
  await capturedReady.fulfill({ json: { status: "ready" } });

  await expect(page.locator(".probe-badge").filter({ hasText: "READY" })).toContainText("online");
  await expect(run).toBeEnabled();
});

test("keeps Run disabled when readiness is offline", async ({ page }) => {
  await mockWorkbench(page, { ready: (route) => route.abort() });
  await openLoadedWorkbench(page);

  await expect(page.locator(".probe-badge").filter({ hasText: "READY" })).toContainText("offline");
  await expect(page.getByRole("button", { name: /Run analysis/ })).toBeDisabled();
});

test("browses v2 research metadata and executes its OpenAPI route", async ({ page }) => {
  const researchPrefix = "/v1/research/proteogenomic-state";
  const catalogOperation = (
    method: "GET" | "POST",
    suffix: "profile" | "demo" | "analyze" | "verify",
    overrides: Record<string, unknown> = {},
  ) => ({
    operation_id: `research_state_${suffix}`,
    method,
    path: `${researchPrefix}/${suffix}`,
    summary: `${suffix} research state`,
    tags: ["research-ecgi"],
    request_media_types: method === "POST" ? ["application/json"] : [],
    response_media_types: ["application/json"],
    parameter_locations: [],
    request_max_bytes: method === "POST" ? 2 * 1024 * 1024 : null,
    result_max_bytes: 4 * 1024 * 1024,
    safety_class: "research-use-only",
    mutability_class: method === "GET" ? "read-only" : suffix === "verify" ? "verification" : "stateless-compute",
    validated_example_status: suffix === "analyze" ? "validated" : "abstained",
    validated_example_id: suffix === "analyze" ? "synthetic-glioma-demo-v1" : null,
    validated_example_abstention_reason: suffix === "analyze"
      ? null
      : method === "GET"
        ? "operation_has_no_request_body"
        : "requires_prior_operation_result",
    ...overrides,
  });
  const operations = [
    catalogOperation("GET", "profile"),
    catalogOperation("GET", "demo"),
    catalogOperation("POST", "analyze"),
    catalogOperation("POST", "verify", { request_max_bytes: 7 * 1024 * 1024 }),
  ];
  const operationDocument = (suffix: string, hasBody = false) => ({
    summary: `${suffix} research state`,
    operationId: `research_state_${suffix}`,
    ...(hasBody ? {
      requestBody: {
        required: true,
        content: {
          "application/json": {
            schema: {
              type: "object",
              properties: { sample_id: { type: "string", default: "synthetic-demo" } },
            },
          },
        },
      },
    } : {}),
  });
  let legacyCatalogRequests = 0;
  let submittedPayload: unknown = null;
  page.on("request", (request) => {
    if (request.url().includes("/backend/v1/deployment/catalog")) legacyCatalogRequests += 1;
  });
  await Promise.all([
    page.route("**/backend/livez", (route) => route.fulfill({ json: { status: "ok" } })),
    page.route("**/backend/readyz", (route) => route.fulfill({ json: { status: "ready" } })),
    page.route("**/backend/v2/deployment/catalog", (route) => route.fulfill({ json: {
      catalog_version: 2,
      environment: "test",
      version: "1.0.0",
      operation_count: operations.length,
      operations,
      catalog_digest: "sha256:abababababababababababababababababababababababababababababababab",
    } })),
    page.route("**/backend/openapi.json", (route) => route.fulfill({ json: {
      openapi: "3.1.0",
      paths: {
        [`${researchPrefix}/profile`]: { get: operationDocument("profile") },
        [`${researchPrefix}/demo`]: { get: operationDocument("demo") },
        [`${researchPrefix}/analyze`]: { post: operationDocument("analyze", true) },
        [`${researchPrefix}/verify`]: { post: operationDocument("verify", true) },
      },
    } })),
    page.route(`**/backend${researchPrefix}/analyze`, async (route) => {
      submittedPayload = route.request().postDataJSON();
      await route.fulfill({ json: { status: "complete", receipt_id: "receipt.console-test" } });
    }),
  ]);

  await page.goto("/api-console");
  await expect(page.getByRole("heading", { name: "GLIO Proteogen" })).toBeVisible();
  await expect(page.getByText("Run evidence-grade model routes with context.")).toBeVisible();
  await expect(page.getByText("Mounted operations")).toBeVisible();
  expect(legacyCatalogRequests).toBe(0);

  await page.getByLabel("Search operation catalog").fill("research-use-only");
  await expect(page.locator(".module-item")).toHaveCount(4);
  await page.getByRole("button", { name: `POST ${researchPrefix}/analyze` }).click();

  await expect(page.locator(".limit-grid")).toContainText("2.0 MB");
  await expect(page.locator(".limit-grid")).toContainText("4.0 MB");
  const metadata = page.locator('[aria-label="Operation catalog metadata"]');
  await expect(metadata).toContainText("research-use-only");
  await expect(metadata).toContainText("stateless-compute");
  await expect(metadata).toContainText("validated");
  await expect(metadata).toContainText("synthetic-glioma-demo-v1");
  await expect(metadata).toContainText("research-ecgi");
  await expect(metadata).toContainText("application/json");

  const payload = page.getByLabel("Request payload JSON");
  await expect(payload).toContainText('"sample_id": "synthetic-demo"');
  await payload.fill(JSON.stringify({ sample_id: "console-execution" }));
  await page.getByRole("button", { name: "Run request" }).click();
  await expect(page.locator(".response-panel")).toContainText("receipt.console-test");
  expect(submittedPayload).toEqual({ sample_id: "console-execution" });

  await page.getByRole("button", { name: `GET ${researchPrefix}/profile` }).click();
  await expect(metadata).toContainText("abstained");
  await expect(metadata).toContainText("operation_has_no_request_body");
});
