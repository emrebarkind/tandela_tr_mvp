import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  webpack(config) {
    config.resolve.alias["@splinetool/react-spline"] = path.join(
      __dirname,
      "node_modules/@splinetool/react-spline/dist/react-spline.js",
    );
    return config;
  },
};

export default nextConfig;
