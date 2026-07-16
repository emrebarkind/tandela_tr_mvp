import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const backendOrigin = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/:path*`,
      },
    ];
  },
  webpack(config) {
    config.resolve.alias["@splinetool/react-spline"] = path.join(
      __dirname,
      "node_modules/@splinetool/react-spline/dist/react-spline.js",
    );
    return config;
  },
};

export default nextConfig;
