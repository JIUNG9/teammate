/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",  // for k8s container deploy
  // Proxy /api/* to the teammate-chat-api service in-cluster
  async rewrites() {
    const apiUrl = process.env.TEAMMATE_CHAT_API_URL || "http://teammate-chat-api.teammate-agent.svc.cluster.local";
    const warUrl = process.env.TEAMMATE_WAR_API_URL  || "http://teammate-war-api.teammate-agent.svc.cluster.local";
    return [
      { source: "/api/chat/:path*", destination: `${apiUrl}/:path*` },
      { source: "/api/war/:path*",  destination: `${warUrl}/:path*` },
    ];
  },
};
export default nextConfig;
