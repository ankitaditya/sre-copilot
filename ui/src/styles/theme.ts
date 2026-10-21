import {
  createDarkTheme,
  createLightTheme,
  type BrandVariants,
} from "@fluentui/react-components";

const operationsBrand: BrandVariants = {
  10: "#020406",
  20: "#071B2B",
  30: "#092B43",
  40: "#0A3857",
  50: "#0B466C",
  60: "#0B5482",
  70: "#096399",
  80: "#0872B0",
  90: "#2788BF",
  100: "#459DCD",
  110: "#62B1DA",
  120: "#80C5E6",
  130: "#A0D7EF",
  140: "#C1E7F6",
  150: "#DDF3FA",
  160: "#F2FBFD",
};

export const lightTheme = createLightTheme(operationsBrand);
export const darkTheme = createDarkTheme(operationsBrand);
