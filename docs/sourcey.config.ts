import { defineConfig, markdown } from "sourcey";

export default defineConfig({
  name: "Vendor Fabric",
  siteUrl: "https://jonbogaty.com",
  baseUrl: "/vendor-fabric",
  repo: "https://github.com/jbcom/vendor-fabric",
  editBranch: "main",
  prettyUrls: "slash",
  theme: {
    preset: "default",
    colors: {
      primary: "#344f9f",
      light: "#5874c5",
      dark: "#1f3474",
    },
    fonts: {
      sans: "Inter",
      mono: "JetBrains Mono",
    },
    layout: {
      sidebar: "18rem",
      toc: "18rem",
      content: "48rem",
    },
    css: ["./assets/vendor-fabric.css"],
  },
  logo: {
    light: "./assets/vendor-fabric-mark-light.svg",
    dark: "./assets/vendor-fabric-mark-dark.svg",
    href: "/vendor-fabric/",
  },
  favicon: "./assets/vendor-fabric-favicon.svg",
  navbar: {
    links: [{ type: "github", href: "https://github.com/jbcom/vendor-fabric" }],
  },
  footer: {
    links: [{ type: "github", href: "https://github.com/jbcom/vendor-fabric" }],
  },
  navigation: {
    tabs: [
      {
        tab: "Guides",
        slug: "",
        source: markdown({
          groups: [
            { group: "Start here", pages: ["index", "installation", "connectors"] },
            { group: "Architecture", pages: ["architecture", "pillars", "ownership"] },
            { group: "Operations", pages: ["secrets-sync", "testing", "contributing"] },
          ],
        }),
      },
      {
        tab: "Reference",
        slug: "reference",
        source: markdown({
          groups: [{ group: "Python API", pages: ["reference/api"] }],
        }),
      },
    ],
  },
});
