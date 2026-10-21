import { describe, expect, it } from "vitest";
import { signTC3 } from "../src/core/tc3.js";

describe("signTC3", () => {
  it("生成 TC3-HMAC-SHA256 授权头", () => {
    const signed = signTC3({
      secretId: "AKIDEXAMPLE",
      secretKey: "SECRETKEYEXAMPLE",
      service: "cvm",
      action: "DescribeInstances",
      version: "2017-03-12",
      region: "ap-guangzhou",
      payload: "{}",
      timestamp: 1551113065,
    });

    expect(signed.url).toBe("https://cvm.tencentcloudapi.com/");
    expect(signed.headers["X-TC-Action"]).toBe("DescribeInstances");
    expect(signed.headers["X-TC-Version"]).toBe("2017-03-12");
    expect(signed.headers["X-TC-Region"]).toBe("ap-guangzhou");
    expect(signed.headers.Authorization).toMatch(
      /^TC3-HMAC-SHA256 Credential=AKIDEXAMPLE\/2019-02-25\/cvm\/tc3_request, SignedHeaders=content-type;host;x-tc-action, Signature=[0-9a-f]{64}$/,
    );
  });

  it("日期由 timestamp 推导，且签名稳定", () => {
    const options = {
      secretId: "id",
      secretKey: "key",
      service: "dnspod",
      action: "DescribeDomainList",
      version: "2021-03-23",
      payload: '{"Limit":10}',
      timestamp: 1_700_000_000,
    } as const;

    const a = signTC3(options);
    const b = signTC3(options);
    expect(a.headers.Authorization).toBe(b.headers.Authorization);
    expect(a.headers.Authorization).toContain("/2023-11-14/dnspod/tc3_request");
    expect(a.headers["X-TC-Region"]).toBeUndefined();
  });

  it("临时凭据会带上 X-TC-Token", () => {
    const signed = signTC3({
      secretId: "id",
      secretKey: "key",
      token: "sts-token",
      service: "sts",
      action: "GetCallerIdentity",
      version: "2018-08-13",
      payload: "{}",
    });
    expect(signed.headers["X-TC-Token"]).toBe("sts-token");
  });
});
