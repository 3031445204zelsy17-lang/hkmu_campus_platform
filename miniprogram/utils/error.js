/** FR7b:按错误类型返回友好 i18n 文案。
 * err.type 由 request.js 设置:network(断网)/timeout(超时)/server(5xx)/client(4xx)。
 * text 需含 errorNetwork/errorTimeout/errorServer(loadFail 兜底)——都在 i18n COMMON scope。
 */

function describeError(err, text) {
  const type = (err && err.type) || "network";
  const fallback = (text && text.loadFail) || "Load failed";
  if (type === "timeout") return (text && text.errorTimeout) || fallback;
  if (type === "server") return (text && text.errorServer) || fallback;
  // client(4xx):用后端返回的 message(如"内容包含违规信息"),更具体
  if (type === "client") return (err && err.message) || fallback;
  return (text && text.errorNetwork) || fallback; // network / unknown
}

module.exports = { describeError };
