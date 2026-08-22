import {
  defaultValues,
  TemplateFormValues,
} from "../components/templates/TemplateForm/TemplateForm";
import { PlaceholderLogoKind } from "./generatePlaceholderLogo";

export interface TemplatePreset {
  id: string;
  name: string;
  description: string;
  values: TemplateFormValues;
  // Generated on the fly and uploaded as this preset's starting logo the moment it's
  // picked (see generatePlaceholderLogo.ts) -- a real, org-owned logo from the start, not
  // just a cosmetic thumbnail, since a shared/global logo key can't exist across orgs
  // (every logoKey is scoped to the org that uploaded it).
  logoKind: PlaceholderLogoKind;
}

type PresetOverrides = Partial<Omit<TemplateFormValues, "header" | "style">> & {
  header?: Partial<TemplateFormValues["header"]>;
  style?: Partial<TemplateFormValues["style"]>;
};

// Each preset starts from the same section/footer/doctorInfo defaults everything else in
// the app already uses (`defaultValues()`, TemplateForm.tsx) and only varies name/color/
// font -- so a preset is just a different starting point for the same fully-customizable
// form, never a separate code path.
function preset(overrides: PresetOverrides): TemplateFormValues {
  const base = defaultValues();
  return {
    ...base,
    ...overrides,
    header: { ...base.header, ...overrides.header },
    style: { ...base.style, ...overrides.style },
  };
}

export const TEMPLATE_PRESETS: TemplatePreset[] = [
  {
    id: "classic",
    name: "Radiology Classic",
    description: "Traditional black-on-white letterhead with a teal accent.",
    values: preset({
      name: "Radiology Classic",
      accentColor: "#0E7C86",
      style: { headerTextColor: "#0E7C86" },
    }),
    logoKind: "cross",
  },
  {
    id: "modern-blue",
    name: "Modern Blue",
    description: "A bold blue header for a contemporary look.",
    values: preset({
      name: "Modern Blue",
      accentColor: "#1D4ED8",
      style: { headerTextColor: "#1D4ED8" },
    }),
    logoKind: "pulse",
  },
  {
    id: "warm-neutral",
    name: "Warm Neutral",
    description: "Soft warm tones for a friendlier, outpatient-facing report.",
    values: preset({
      name: "Warm Neutral",
      accentColor: "#B45309",
      style: { headerTextColor: "#B45309", contentTextColor: "#3F2E1E" },
    }),
    logoKind: "shield",
  },
  {
    id: "high-contrast",
    name: "High Contrast",
    description: "Larger type and bold color for maximum legibility.",
    values: preset({
      name: "High Contrast",
      style: { headerTextColor: "#111827", fontSize: 12 },
    }),
    logoKind: "bold-cross",
  },
  {
    id: "clinical-green",
    name: "Clinical Green",
    description: "A calm green accent with a clean, practical report layout.",
    values: preset({
      name: "Clinical Green",
      accentColor: "#166534",
      style: { headerTextColor: "#166534" },
    }),
    logoKind: "shield",
  },
];
