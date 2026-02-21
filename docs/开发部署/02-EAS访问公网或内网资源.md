# 配置 EAS 专有网络实现公网访问与内网互通

> 来源：https://help.aliyun.com/zh/pai/user-guide/configure-network-connectivity

当 EAS 服务需要调用公网 API、从公网下载文件、连接 RDS 数据库或访问其他外部服务时，需为其配置专有网络（VPC）以实现网络连通。

---

## 工作原理

为 EAS 服务配置 VPC 后，系统会为服务的每个实例创建一个弹性网卡（ENI），并占用指定交换机的一个私网 IP 地址，使服务实例获得 VPC 内的网络身份，从而实现与 VPC 内其他资源的网络互通，或通过 VPC 内的 NAT 网关访问公网。

> **通俗理解**：EAS 服务默认是一个"封闭"的环境，配置 VPC 就像是给服务开了一扇"门"，让它可以与其他云服务或互联网通信。

---

## 计费说明

为 EAS 服务配置 VPC 本身**不产生费用**，但用于访问公网的 **NAT 网关** 和 **弹性公网 IP（EIP）** 均为付费产品。

- **NAT 网关计费**：参见 [NAT 网关计费](https://help.aliyun.com/zh/nat-gateway/nat-gateway-billing)
- **EIP 计费**：参见 [EIP计费概述](https://help.aliyun.com/zh/eip/product-overview/billing-overview/)

---

## 开始之前：网络规划与准备

在配置前，请先规划网络连接方式，并准备好所需的 VPC、交换机和安全组。

### 网络规划建议

1. **确认访问需求**：您的 EAS 服务需要访问公网还是仅需内网互通？
   - **公网访问**：需要配置 VPC + 交换机 + NAT 网关 + EIP
   - **内网互通**：只需配置 VPC + 交换机（EAS 服务与目标服务在同一 VPC 内）

2. **选择网络方案**：
   - **私网互通最简方式**：将 EAS 服务与目标服务部署在**同一 VPC** 内
   - **跨 VPC 互通**：需要通过 [VPC 对等连接](https://help.aliyun.com/zh/vpc/vpc-peer-to-peer-connection) 或 [云企业网](https://help.aliyun.com/zh/cen/product-overview/what-is-cen/) 打通网络

### 准备工作

如需创建 VPC、交换机和安全组，请参见：
- [创建专有网络与交换机](https://help.aliyun.com/zh/vpc/vpc-and-vswitch)
- [使用安全组](https://help.aliyun.com/zh/ecs/user-guide/start-using-security-groups)

> **注意**：所有 EAS 服务的出流量均受安全组规则限制。请确保安全组的出方向规则允许 EAS 服务访问目标服务。

---

## 操作步骤

### 步骤 1：为 EAS 服务配置专有网络

为 EAS 服务配置专有网络是实现内网互通或公网访问的基础。EAS 支持在**服务级别**和**资源组级别**配置 VPC：

| 级别 | 说明 | 优先级 |
|------|------|--------|
| 服务级别 | 为单个服务指定 VPC | 最高 |
| 资源组级别 | 为使用专属资源组部署的服务设置默认 VPC | 较低 |

> **说明**：若服务级别和资源组级别同时配置，**以服务级别为准**。

#### 方式一：通过控制台配置

创建或更新服务时，在**网络信息**区域，进行专有网络配置。下拉选择专有网络之后，再配置交换机和安全组。

#### 方式二：通过 eascmd 客户端工具配置

1. 在服务的 JSON 配置文件中添加或修改 `cloud.networking` 字段：

   ```json
   {
       "cloud": {
           "networking": {
               "vpc_id": "your-vpc-id",
               "vswitch_id": "your-switch-id",
               "security_group_id": "your-security-group-id"
           }
       }
   }
   ```

   - `vpc_id`：专有网络 ID，可在 [VPC 控制台](https://vpc.console.aliyun.com/) 查询
   - `vswitch_id`：交换机 ID
   - `security_group_id`：安全组 ID，可在 [ECS 安全组](https://ecs.console.aliyun.com/securityGroup) 页面查询

2. 使用 `create` 或 `modify` 命令创建服务或修改服务配置。详见 [eascmd 命令使用说明](https://help.aliyun.com/zh/pai/developer-reference/run-commands-to-use-the-eascmd-client)。

#### 方式三：资源组级别配置（可选）

如果需要为整个资源组统一配置 VPC：

- **控制台**：在**资源组**页面，选择目标资源组，单击**操作**列的**开启 VPC 配置**
- **eascmd 工具**：请参见 [配置资源组专有网络](https://help.aliyun.com/zh/pai/developer-reference/run-commands-to-use-the-eascmd-client#title-2q6-lrf-hvp)

---

### 步骤 2：配置公网 NAT 网关与 SNAT 条目

> **此步骤仅适用于需要访问公网的情况**。如果您的 EAS 服务只需要内网互通，可以跳过此步骤。

如果 EAS 服务需要访问互联网，需借助 NAT 网关和 EIP。

#### 2.1 创建公网 NAT 网关并绑定 EIP

1. 前往 [NAT 网关 - 公网 NAT 网关购买页](https://vpc.console.aliyun.com/buy/nat)
2. 选择 EAS 服务所在的地域和 VPC
3. 为其绑定一个 EIP（此 EIP 将作为 EAS 服务访问公网的统一出口 IP）

#### 2.2 配置 SNAT 条目

在已创建的 NAT 网关中，创建一条 SNAT 条目：

- **SNAT 条目粒度**：选择 **VPC 粒度**
- 这样，该 VPC 内发往公网的流量将通过此 NAT 网关发出

> **什么是 SNAT？** SNAT（Source Network Address Translation）用于让 VPC 内的云服务能够访问公网，同时隐藏内部 IP 地址。

---

### 步骤 3：配置白名单（可选）

如果目标服务（无论是内网还是公网）开启了 IP 或安全组白名单限制，需要将 EAS 服务的 IP 地址段或者安全组 ID 添加到目标服务的白名单中。

#### 获取内网 IP 地址

**重要**：EAS 的实例是动态调度的，重启或更新后可能会在新的物理节点上创建新实例，并从交换机地址池中获取一个新的**私网 IP 地址**。因此，依赖 IP 的访问控制策略应使用**交换机网段**，而不是写死单个实例的 IP。

**查询方法**：
1. 登录 [专有网络 VPC 控制台](https://vpc.console.aliyun.com/)
2. 在**交换机**页面查询对应 IPv4 网段

#### 获取公网 IP 地址

1. 登录 [专有网络 VPC 控制台](https://vpc.console.aliyun.com/)
2. 进入 **NAT 网关** > **公网 NAT 网关** 页面
3. 找到为 EAS 配置的网关，在**弹性公网 IP** 列查看绑定的 EIP 地址

---

## 生产应用建议

### 1. IP 地址规划

为 EAS 服务规划独立的、IP 数量充足的**交换机**。

所需 IP 数至少应为：`稳定运行实例数 + 滚动更新时额外实例数 + 预留缓冲IP`

> **注意**：IP 不足将导致服务创建或扩容失败。

### 2. 安全组隔离

- 为不同服务或不同环境（开发、测试、生产）使用独立的安全组
- 遵循最小权限原则，仅开放必要的端口和访问源

### 3. 成本优化

若 EAS 服务需要访问公网下载模型或文件，最佳方案是将资源上传至**同地域的 OSS**，在部署时挂载 OSS。这样可以避免使用公网产生费用。

---

## 常见问题

### Q：为什么 EAS 默认无法访问公网？

EAS 服务默认限制公网访问，主要是出于安全性和稳定性考虑：
- 公网出口带宽在共享环境中容易被滥用
- 带宽资源存在不确定性与波动，会直接影响服务的性能表现和可用性

如有需要时可自行配置专有网络的公网访问。

---

### Q：如何快速验证服务能否访问公网？

可以在服务配置的**运行命令**中添加网络测试指令：

```bash
curl -I -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0" --connect-timeout 5 https://www.aliyun.com
```

部署后查看实例的**实时日志**，如果看到 `200` 等状态码，则表示公网已连通。

---

### Q：配置了 VPC 后，为何仍无法内网访问 VPC 内的云产品？

请按以下顺序排查：

1. **VPC 配置**：确认 EAS 服务与目标服务处于同一个 VPC 内
2. **安全组规则**：确认 EAS 服务配置的安全组出方向规则允许其访问目标服务
3. **目标云产品的访问限制**：如果目标云产品通过 IP 白名单或者安全组限制外部访问，请确认已正确添加 EAS 服务所在的**交换机网段**或安全组

---

### Q：配置了 NAT 网关，为何服务仍无法访问公网？

请按以下顺序排查：

1. **SNAT 规则**：确认 SNAT 条目中的交换机与部署 EAS 服务时指定的交换机一致
2. **VPC 路由表**：在 VPC 控制台检查路由条目列表，确认存在一条目标网段为 `0.0.0.0/0`、下一跳指向 NAT 网关的路由
3. **安全组出方向规则**：确认 EAS 服务所在安全组的出方向规则允许所有公网访问（默认为 `0.0.0.0/0` 允许）
