# qmt量化交易系统 (QmtQuant) - 快速入门手册

> **注意**: 本文档是 qmt量化交易系统 (QmtQuant) 的快速入门指南。

---

## 📖 关于本开源代码

本仓库提供的是 qmt量化交易系统的**完整后端源码**，面向具备 Python 编程基础的开发者和量化研究人员。

**本仓库专注于后端功能与 CLI 工具开发。**

🔧 **主要 CLI 工具**：

- **`bt_cli.py`** — 回测 CLI 入口，支持加载 `.qmt` 配置文件运行回测、查看结果
- **`dm_cli.py`** — 数据管理 CLI 入口，支持数据同步、补充、校验、清理等操作
- **`scheduler_service.py`** — 定时调度服务，用于自动化策略执行

🔗 **获取源码**：

```bash
git clone <项目仓库地址>
cd QmtQuant
pip install -r requirements.txt
```

---

# 第一章：引言：为什么选择qmt量化

## 1.2 我为什么要做这样一款量化交易系统？

市面上的量化工具不少，为何还要"重复造轮子"？核心在于对现有工具的些许不满，以及一些亟待实现的功能与理念。

回测系统是量化交易的基石，它允许策略在历史数据中"演练"，评估可行性。然而，不少现有工具，如QMT，虽具备回测功能，但在策略开发的灵活性上（如Python第三方库的调用）存在限制，这束缚了AI等前沿算法的应用。QmtQuant的初衷便是**打破这些枷锁，赋予开发者最大的策略实现自由度**，让Python的强大生态充分助力创新。

**关键考量：**

* **策略安全与本地运行**：策略是核心资产。QmtQuant基于MiniQMT开发，确保策略代码和数据在本地运行，保障安全与隐私，同时在处理大规模数据或复杂模型时更具性能与成本优势。
* **打造趁手的"兵器"**：工具应保证专业性的同时，追求高效易用。作为一名长期从事信号处理与机器学习算法研究的开发者，深谙此道。QmtQuant力求成为一款称手好用的工具，让用户能更专注于策略研究本身。
* **填补MiniQMT生态空白**：目前市场缺乏针对MiniQMT完善易用的回测与模拟平台。QmtQuant愿做"第一个吃螃蟹的人"，为MiniQMT用户和量化爱好者提供新选择。

**QmtQuant的核心设计原则：**

1. **模块低耦合——提升灵活性与可维护性**：
   借鉴"乐高积木"的理念，QmtQuant追求UI、数据、策略与核心框架的分离。如此，各模块可独立升级、替换，避免"牵一发而动全身"，保证系统未来的迭代与扩展能力。
2. **策略高内聚——聚焦策略，提升效率**：
   使用者应专注于策略逻辑。QmtQuant致力于提供稳定的底层支撑和清晰的接口规范，目标是实现策略文件在回测、模拟、实盘间无缝切换，并共享统一的图形化配置界面，最大程度减轻用户负担。未来，甚至期望通过标准化的接口，结合大语言模型辅助策略生成。

> 💡 **一言以蔽之**：QmtQuant并非追求"大而全"，而是力求在**本地化、灵活性和实用性**这些核心痛点上做到"精而深"，为个人投资者提供一款免费、强大且称手的量化研究利器。

---

## 1.3 qmt量化系统：特点与比较

为了让大家更清晰地理解QmtQuant的定位，这里通过一个简明扼要的表格来对比其与市面上其他主流类型量化工具的特点：


| 特性维度         | qmt量化交易系统 (QmtQuant)                               | 国内券商平台 (如：QMT自带, 通达信) | 开源回测框架 (如：Backtrader, vn.py)          | 在线量化平台 (如：聚宽, BigQuant) |
| :--------------- | :--------------------------------------------------------- | :--------------------------------- | :---------------------------------------------- | :-------------------------------- |
| **系统设计侧重** | CLI/后端工具，与MiniQMT深度集成，实现数据接口**开箱即用** | 账户直连，行情交易便捷，低成本     | 高度灵活定制，免费开源                | 云端运行，提供数据，学习资源丰富  |
| **系统当前局限** | 生态初期，功能待完善，依赖MiniQMT，个人维护                | 策略自由度低，回测功能较弱         | 上手门槛高，需自行寻找、配置和维护数据/交易接口 | 核心代码/数据不可控，高级功能收费 |
| **目标用户画像** | 具备Python基础的量化开发者，希望数据策略本地化             | 普通交易者，编程能力要求不高       | 编程能力强的开发者，需深度定制                  | 量化初学者，偏好云端服务          |
| **策略编程**     | Python                                                     | 平台特定语言或脚本                 | Python                                          | Python为主                        |
| **数据获取**     | **内置MiniQMT接口，开箱即用**                              | 提供多品种行情数据                 | 需用户自行对接和维护数据源                      | 平台提供常用数据                  |
| **界面形态**     | CLI 命令行工具                                             | 标准的行情交易软件界面             | 部分框架提供GUI（如vn.py），其他需自行绘图      | Web界面，图表友好                 |
| **使用成本**     | 免费                                                       | 开户后免费使用                     | 免费                                            | 免费入门，增值服务收费            |

> 简单来说，QmtQuant致力于为A股个人投资者，提供一个在**本地化、简单实用**方面表现出色的量化工具。其与MiniQMT的深度整合，让用户免去了寻找和配置数据源的繁琐工作，可以更专注于策略开发本身。它或许并非完美无瑕，但会持续打磨与进化，力求帮助每一位使用者更高效地进行策略研究与交易实践。

---

选择"qmt量化交易系统"，将能深入体验到以下几点核心优势所带来的便利与价值：

**🎨 完全开源免费**：
QmtQuant 源代码完全公开透明，允许自由探索其实现细节，根据自身需求进行个性化修改。这种开放性，确保了对工具的完全掌控，而不必担心任何"黑箱"操作或潜在的隐性成本。

**🛡️ 数据与策略本地化部署，安全与隐私尽在掌握**：
在量化交易领域，数据和策略无疑是核心资产。QmtQuant 坚持将所有策略代码、历史数据、回测结果以及交易记录等敏感信息完全存储于本地计算机。这意味着使用者对其知识产权和交易活动拥有绝对的控制权，无需担心因依赖第三方云平台而可能带来的数据泄露、策略被窥探或服务中断的风险。智慧成果得以自主守护。

**⚙️ CLI 工具驱动，Python 代码灵活驱动，专注后端功能**：
系统提供了完整的 CLI 命令行工具（`bt_cli.py`、`dm_cli.py`），支持通过命令行完成回测运行、数据管理等核心操作，适合脚本化、自动化的工作流。同时，对于追求极致灵活性和复杂逻辑实现的专业开发者，QmtQuant 提供了纯粹的Python策略编写环境，允许充分利用Python的强大表达能力和丰富的第三方库，构建高度定制化的交易系统。

**🧠 拥抱AI浪潮，为大模型赋能量化策略，拓展智能边界**：
人工智能飞速发展的时代，大语言模型（LLM）的能力令人瞩目。QmtQuant 在设计之初便充分考虑了与AI技术的结合潜力。其清晰的模块划分、标准化的策略接口以及开放的Python环境，都为大模型在量化策略中的应用提供了便利。可以尝试使用大模型辅助进行策略逻辑的构思、代码片段的生成，甚至在未来，期望能实现更深度的融合，让AI成为策略研究与开发过程中的得力助手。

**🔗 深度整合MiniQMT，共享成熟稳定的交易执行**：
QmtQuant 的行情获取深度依赖于券商的MiniQMT系统。这意味着可以直接受益于券商提供的成熟、稳定、合规的行情服务，从而能够更专注于策略本身的研发与优化。

**🎯 专注A股优化，更懂本土化交易者的实战需求**：
与其他通用型或主要面向海外市场的量化平台不同，QmtQuant 在设计和功能实现上，充分考虑了A股市场的独特性。例如，针对A股的交易规则（如T+1制度、涨跌停限制）、常用的技术指标偏好、数据特点等都进行了细致的适配和优化，力求为国内投资者提供一个更接地气、更符合实战需求的量化工具。

**🚀 极致策略自由度，释放Python生态的无限潜能**：
许多量化平台会对可使用的Python第三方库施加诸多限制，这无疑束缚了策略的创新空间。QmtQuant 则致力于打破这些"枷锁"，允许在策略中无拘无束地引入和使用Python生态中几乎所有的公开库。无论是用于高级数据分析的Pandas、NumPy、SciPy，还是用于机器学习的Scikit-learn、TensorFlow、PyTorch，亦或是其他专业领域的强大工具，只要认为对策略有益，都可以自由集成，从而将最前沿的技术和算法应用于量化实践中。

---

## 1.4 使用"qmt量化交易平台"的背景知识清单

为了帮助不同需求的用户更好地使用"qmt量化交易平台"，这里梳理了一份背景知识清单，分为入门、进阶和高级三个层次。您可以根据自己的目标和现有基础，按图索骥，逐步提升。

### 1.4.1 入门：编写开环策略实现回测

此阶段的目标是能够使用已经打包好的"qmt量化平台"，编写并运行开环策略（即策略逻辑相对简单，不涉及复杂的模型训练和动态调优），并对策略进行历史回测，分析回测结果。


| 掌握程度 | 技能                               | 说明                                                                                      |
| :------- | :--------------------------------- | :---------------------------------------------------------------------------------------- |
| **必备** | Python编程基础（含Pandas/NumPy库） | 理解Python核心语法、控制流、函数，并掌握Pandas进行数据处理及NumPy进行数值计算的基本操作。 |
| **必备** | 基本的金融市场知识                 | 了解股票、K线、交易规则、常用技术指标（如均线、MACD、布林带等）的基本概念。               |
| **必备** | 理解回测报告中的关键指标           | 如收益率、最大回撤、夏普比率等。                                                          |
| **必备** | 代码编辑器/IDE的使用               | 熟练使用至少一种代码编辑工具（如VS Code, PyCharm等）进行策略脚本的编写与管理。            |

### 1.4.2 进阶：编写需模型训练的闭环策略实现回测

此阶段的目标是能够在入门基础上，进一步编写包含机器学习、深度学习等模型训练的闭环策略。这类策略通常需要根据市场反馈动态调整模型参数或交易逻辑。


| 掌握程度 | 技能                                         | 说明                                                                                    |
| :------- | :------------------------------------------- | :-------------------------------------------------------------------------------------- |
| **必备** | 扎实的Python编程能力                         | 包括面向对象编程（OOP）思想、模块化编程等。                                             |
| **必备** | Pandas/NumPy高级应用                         | 能够进行更复杂的数据转换、特征工程、性能优化等。                                        |
| **必备** | 机器学习/深度学习基础理论                    | 理解常见的监督学习、无监督学习算法原理，如线性回归、逻辑回归、决策树、SVM、神经网络等。 |
| 建议掌握 | TensorFlow/PyTorch等深度学习框架（至少一种） | 如果策略涉及深度学习模型，需要掌握至少一个主流框架的使用。                              |
| 建议掌握 | 特征工程方法                                 | 如何从原始数据中提取、构建对模型有效的特征。                                            |
| 建议掌握 | 模型评估与调优技巧                           | 了解过拟合、欠拟合，掌握交叉验证、网格搜索等模型调优方法。                              |

### 1.4.3 高级：使用开源代码，定制化修改平台

此阶段的目标是具备深入理解并修改"qmt量化平台"源代码的能力，根据自身特殊需求进行二次开发和功能定制。


| 掌握程度 | 技能                                | 说明                                                                             |
| :------- | :---------------------------------- | :------------------------------------------------------------------------------- |
| **必备** | 精通Python高级编程                  | 深入理解Python的内部机制，如装饰器、生成器、元类、异步编程等。                   |
| **必备** | 深入理解`xtquant` 库 (MiniQMT接口) | 掌握MiniQMT的核心API调用，包括行情订阅、交易指令发送、账户信息查询等。           |
| **必备** | 软件架构设计能力                    | 能够理解和设计模块化、可扩展、可维护的软件系统，理解QmtQuant的现有三层架构。      |
| **必备** | Git版本控制                         | 熟练使用Git进行代码版本管理与协作。                                              |
| **必备** | 量化交易系统核心组件的理解          | 深入理解事件驱动、行情处理、订单管理、风险控制、绩效计算等核心模块的原理与实现。 |
| 建议掌握 | Python多线程/异步编程               | 用于优化后台服务响应、处理耗时操作等，提高平台性能。                             |
| 建议掌握 | 事件驱动编程模型                    | 深入理解事件驱动架构，有助于更好地理解和修改平台的核心逻辑。                     |
> ✨ **小贴士**：对于绝大多数希望进行策略回测和研究的用户来说，达到"入门"级别并逐步熟悉平台功能，就已经能够满足大部分需求。"qmt量化平台"也会持续推出更多策略示例和教程，帮助大家更好地理解和应用。

---

## 1.5 "qmt量化交易系统"适合做什么？

"qmt量化交易系统"以其灵活性和易用性，能够很好地支持多种类型的中低频量化交易策略的研发与实践。以下是一些典型的适用场景：

* ✅ **各类因子选股与轮动策略**：无论是基于经典的价值、成长、质量、动量等因子，还是自行构建的特色因子，系统都能方便地进行多因子模型的选股、打分、回测与组合轮动。
* ✅ **趋势跟踪与技术指标策略**：对于依赖均线系统、布林带、MACD、RSI等各类技术指标构建的趋势跟踪、突破或震荡策略，系统提供了良好的支持。
* ✅ **统计套利与均值回归策略**：包括但不限于配对交易、期现套利（基于MiniQMT支持的品种）、ETF套利以及其他利用市场短期失衡的均值回归型策略。
* ✅ **事件驱动型策略**：结合外部事件数据（如财报发布、重要行业新闻、政策变动等），构建在特定事件发生前后进行交易决策的策略。
* ✅ **机器学习与AI辅助策略（中低频）**：利用Scikit-learn、TensorFlow、PyTorch等库，训练机器学习或深度学习模型，对股价走势、市场状态等进行预测，并结合系统生成中低频交易信号。
* ✅ **投资组合管理与动态再平衡**：实现基于特定风险偏好或资产配置模型的投资组合构建，并根据市场变化或预设规则进行定期的动态调仓和再平衡。
* ✅ **自定义指数构建与增强**：根据特定的投资理念或行业偏好，自行编制指数并进行跟踪，或者在现有指数基础上进行Alpha增强。
* ✅ **量化知识学习与策略思想验证**：系统友好的界面和开放的特性，使其成为学习量化交易、快速验证策略思路的理想平台。
* ✅ **成熟交易逻辑的自动化执行**：将经过验证的、系统化的手动交易经验和规则，通过代码实现自动化执行，解放人力，提高效率。

> 总而言之，只要策略的执行频率和对延迟的要求不是极端严苛，QmtQuant 都能提供一个强大而便捷的本地化解决方案。

---

## 1.6 "qmt量化交易系统"不适合做什么？

> ⚠️ **请注意**：虽然"qmt量化交易系统"力求强大与灵活，但基于其设计定位和核心依赖（MiniQMT），在以下一些方面可能并非最佳选择，了解这些局限性有助于用户做出更合理的预期和决策。

* ❌ **高频交易（HFT）与超低延迟策略**：
  * **数据层面**：MiniQMT提供的Tick数据通常是3秒快照，而非逐笔成交数据，这对于需要微秒级行情精度的典型高频策略来说，信息颗粒度不足。
  * **执行层面**：系统本身（Python语言特性、多层架构）以及通过MiniQMT的交易链路，都无法满足高频交易所要求的亚毫秒级执行延迟。
  * **技术栈**：专业的高频交易通常需要C++等高性能语言、FPGA硬件加速以及专用的低延迟交易接口和托管服务。
* ❌ **依赖极久远历史数据的细颗粒度回测**：
  * **MiniQMT数据限制**：券商版MiniQMT对历史数据的下载范围有限制。通常情况下，Tick数据可能只能获取最近一个月左右，1分钟和5分钟K线数据可能为最近一年左右，日线数据则相对完整。这意味着，如果策略需要回测数年前的分钟级甚至Tick级行情，系统可能无法直接提供足够的数据支撑。（有实力的可以开通研投版QMT，这样就有全部的数据了）
* ❌ **对多市场、多资产的复杂联动套利（超出MiniQMT范围）**：
  虽然可以通过Python的灵活性尝试对接其他数据源或接口，但QmtQuant的核心优化和原生支持是围绕MiniQMT所能覆盖的A股市场（股票、ETF、部分期货期权等）。对于需要复杂跨市场（如全球市场）、跨资产类别（如外汇、加密货币）进行高精度、低延迟联动的套利策略，可能需要更专业的、针对性的平台。
* ❌ **非Windows操作系统的原生流畅运行**：
  由于MiniQMT客户端本身主要运行于Windows环境，QmtQuant的主要开发和测试也是在Windows上进行的。虽然技术上用户可能尝试通过Wine等兼容层在Linux或MacOS上运行，但这并非官方支持的路径，可能会遇到稳定性问题或兼容性障碍。

---

# 第二章：重要声明与权责说明

在您使用"qmt量化交易系统"（以下简称"本系统"）之前，请务必仔细阅读并充分理解本章的全部条款。这些条款构成了您与本系统作者之间关于使用本软件的重要约定。

---

## 2.1 系统依赖与免责声明

* **对MiniQMT的依赖**
  本系统的行情数据获取与交易执行功能，完全依赖于您本地安装的券商版MiniQMT客户端。为了实现回测功能，本系统会在本地存储和处理从MiniQMT下载的行情数据，但系统本身不生产任何原始数据。
* **数据验证与检验机制**
  本系统在运行过程中包含了数据有效性检验功能，会对从MiniQMT获取的数据进行基础的完整性和格式校验。但需要明确的是，这些检验仅为程序正常运行的技术保障，**不能等同于对数据准确性的担保**。市场数据的准确性和及时性完全取决于券商MiniQMT及其上游数据源。
* **核心功能定位**
  请注意，当前版本的"qmt量化交易系统"是一款**策略回测与研究平台**，其核心功能是历史数据验证，官方版本不包含任何直接执行实盘交易的功能。
* **全面责任界定**
  本系统作者的责任仅限于提供软件工具本身。**使用本软件过程中遇到的任何问题，包括但不限于系统故障、数据错误、策略失效、操作失误、电脑故障等，均由用户自行承担全部责任**。对于因以下原因导致的任何直接或间接损失，作者不承担任何形式的法律或经济责任：

  1. 券商MiniQMT客户端或其服务器的任何故障、错误、延迟或数据偏差。
  2. 网络连接问题、运营商服务中断等第三方因素。
  3. 用户自行修改代码以启用实盘交易功能后，所产生的一切后果（包括但不限于任何资金损失）。
  4. 本软件自身的任何漏洞、错误、兼容性问题或运行异常。
  5. 用户操作不当、配置错误或对软件功能理解偏差。

---

## 2.2 开源承诺与维护责任

* **免费与开源**
  本系统是一款免费且开放源代码的软件，旨在为A股量化爱好者提供一个高效、便利的研究工具。
* **维护责任限制**
  作者会尽力维护系统的稳定性并进行功能迭代，但无法承诺对每一位用户的特定需求提供即时支持。具体而言：

  * **Bug修复**：将根据严重程度与影响范围进行排序并择机处理。
  * **功能开发**：新功能请求将被纳入待办池，作者会进行评估规划，但无法保证实现时间与具体方案。
  * **代码讲解**：由于精力所限，作者不提供针对开源代码的任何个人化、一对一的教学服务。
* **鼓励自主创新**
  本系统完全开源，对于有特殊或紧急功能需求的用户，我们鼓励并支持您在许可协议范围内，利用源代码自行修改、定制和实现。

---

## 2.3 使用许可协议

本系统的源代码及相关文档遵循 **CC BY-NC 4.0 (署名-非商业性使用 4.0 国际)** 许可协议。

* **您可以自由地**：

  * **分享** — 在任何媒介以任何形式复制、发行本作品。
  * **演绎** — 修改、转换或以本作品为基础进行创作。
* **但必须遵守以下条款**：

  * **署名 (BY)** — 您必须给出适当的署名，提供指向本许可协议的链接，并标明是否对作品作出了修改。
  * **非商业性使用 (NC)** — 您不得将本作品用于任何商业目的。
  * **无附加限制** — 您不得附加任何法律条款或技术措施，从而限制他人行使本许可协议所允许的权利。

#### 严正声明：关于商业使用的规定

任何个人或实体均可在协议范围内，使用本系统代码进行学习研究与自用修改。

**严禁将本系统及其任何衍生版本用于任何形式的商业目的**，包括但不限于：出售软件、以本系统为核心提供任何形式的付费服务、搭建商业化平台等。

任何违反此声明的商业行为所引发的一切法律纠纷、商业风险及经济损失，均由该使用者自行承担。**作者保留对所有侵权行为进行法律追究的权利。**

---

## 2.4 投资风险免责声明

**重要提示：本系统不构成任何投资建议**

1. **教育与研究目的**
   "qmt量化交易系统"及其所有相关内容（包括示例策略、代码、文档等）的唯一目的，是进行量化编程技术交流、策略思想探讨和金融市场研究。
2. **非投资顾问**
   本系统的任何功能、输出信息（如回测报告、性能指标）及示例代码，**均不应被解释为任何形式的投资建议或交易推荐**。历史回测表现不代表未来实际收益，过往的业绩无法预示未来的结果。
3. **用户责任自负**
   您必须基于自身的专业知识、风险承受能力和独立判断来做出投资决策。任何因使用本系统或参考其内容而进行的投资行为，所产生的一切盈利或亏损，**均由您自行承担全部责任**，与本系统作者无任何关系。

**投资有风险，入市需谨慎。**

---

# 第三章：安装与初次配置

在正式开启您的量化之旅前，我们需要确保一切准备就绪。本章将指导您完成运行环境的配置、系统的安装，以及首次启动时的关键设置。这就像战前检查装备，虽显繁琐，却至关重要。

---

## 3.1 运行环境要求

为了让"qmt量化交易系统"在您的电脑上流畅运行，请确保满足以下基本环境要求：

### 3.1.1 硬件与操作系统

* **操作系统**: **Windows 10 或更高版本的64位系统**。

  > 💡 **开发者言**：由于本系统的核心依赖——MiniQMT客户端主要运行于Windows平台，因此QmtQuant的主要开发和测试环境也都在Windows上。虽然理论上可能通过虚拟机或兼容层在其他系统（如macOS, Linux）上运行，但这并非官方支持的路径，可能会遇到各种意想不到的兼容性问题。
  >
* **硬件建议**:

  * **CPU**: 建议使用现代多核处理器（如 Intel i5 或 AMD R5 及以上）。
  * **内存 (RAM)**: 建议 **16GB** 或以上。请注意，内存的实际需求在很大程度上取决于您策略的复杂度和数据处理量。对于涉及大规模数据回测或复杂机器学习模型的策略，更大的内存将显著提升运行效率。我们将在后续的更新中，提供更精确的关于基础软件运行的最低硬件要求。
  * **硬盘**: 建议使用 **固态硬盘 (SSD)**，以加快数据读取和软件启动速度。

### 3.1.2 核心依赖软件

* **MiniQMT 客户端**: **这是本系统运行的绝对前提**。
  您必须首先从您开户的券商处下载并安装最新版的MiniQMT客户端，并确保您能够正常登录您的账户。本系统所有的数据获取和交易指令（若未来支持）都将通过此客户端完成。如尚未开通 miniQMT，请咨询您的券商完成开通。

  成功安装后，打开miniQMT客户端将会显示下边的界面：
* **Microsoft Visual C++ Redistributable**:
  为了确保系统图形界面和部分依赖库的正常工作，您需要安装 `Microsoft Visual C++ 2015-2022 Redistributable (x64)`。

  > 🔗 **官方下载链接**: [https://aka.ms/vs/17/release/vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)
  >
  > **如何检查？** 通常，如果您能正常运行其他大型软件或游戏，这个组件很可能已经安装。如果不确定，直接下载并运行安装程序即可，它会自动判断是否需要安装或修复。
  >

---

## 3.2 qmt量化系统安装

本仓库提供完整后端源码，推荐从源码安装：

```bash
git clone <项目仓库地址>
cd QmtQuant
pip install -r requirements.txt
```

安装完成后可通过 `python bt_cli.py` 、`python dm_cli.py` 等入口脚本启动。

---

## 3.3 配置 MiniQMT 路径

QmtQuant 通过配置文件（`.qmt` JSON 文件）与 MiniQMT 集成。首次使用前，需要在配置文件中设置 MiniQMT 的路径。

**配置文件中的关键字段**：

```json
{
  "xt_client_path": "D:\\国金证券QMT交易端\\bin.x64\\XtItClient.exe",
  "xt_data_path": "D:\\国金证券QMT交易端\\userdata_mini"
}
```

- **`xt_client_path`**：MiniQMT 主程序文件路径（`XtItClient.exe`）
- **`xt_data_path`**：MiniQMT 用户数据文件夹路径（`userdata_mini`）

> 💡 这两个路径通常都在您的 MiniQMT 安装根目录下。

---

## 3.4 启动 MiniQMT

QmtQuant 的数据获取和交易接口依赖 MiniQMT 提供的后台服务。在运行任何 CLI 命令前，请确保：

1. 打开您的券商 MiniQMT 客户端
2. 在登录界面勾选 **"极简模式"**（部分券商版本称为"独立交易"）
3. 成功登录账户

> ⚠️ **重要提示**：必须先成功登录 MiniQMT，CLI 工具才能正常连接数据接口。

---

## 3.5 Mac / Linux 跨平台支持（xqshare）

> **背景**：xtquant 是 Windows 专属的编译库（`.pyd`），无法在 Mac / Linux 上直接运行。xqshare 通过 RPyC 远程调用，将 Windows 机器上的 xtquant 能力透明地暴露给 Mac / Linux 端。

### 3.5.1 架构概览

```
┌──────────────────────────┐         ┌──────────────────────────┐
│   Mac / Linux（开发机）    │  RPyC   │   Windows（MiniQMT 主机）  │
│                          │  18812  │                          │
│  dm_cli.py / bt_cli.py   │ ──────► │  xqshare server          │
│    └─ env.py → xtdata    │ ◄────── │    └─ xtquant（原生）     │
└──────────────────────────┘         └──────────────────────────┘
```

对上层代码完全透明，`from env import xtdata` 的调用方式在所有平台上完全一致。

### 3.5.2 Windows 端配置

**Step 1：安装 xqshare**

```powershell
pip install xqshare
```

**Step 2：环境检测（可选，推荐）**

确保 MiniQMT 已登录运行后，执行：

```powershell
python config/check_env.py
```

脚本会自动检测 Python 版本、xtquant 安装状态、MiniQMT 运行状态，并生成 `.env` 配置文件。

**Step 3：启动 xqshare server**

```powershell
# 后台启动（推荐）
python -m xqshare.server --background
```

启动成功后终端显示：

```
INFO - xqshare server started on 0.0.0.0:18812
INFO - xtdata connected
INFO - xttrader connected
```

> **注意**：Windows 防火墙需允许 18812 端口入站。若使用 Parallels Desktop，VM IP 通常为 `10.211.55.3`。

### 3.5.3 Mac / Linux 端配置

**Step 1：安装 xqshare**

```bash
pip install xqshare
```

**Step 2：配置连接参数**

在项目根目录的 `.env` 文件中添加：

```ini
XQSHARE_REMOTE_HOST=10.211.55.3    # Windows 机器 IP（本机则为 127.0.0.1）
XQSHARE_REMOTE_PORT=18812          # xqshare 服务端口
```

**Step 3：验证连接**

```bash
# 命令行快速验证
xtdata get_stock_list_in_sector --sector-name "沪深A股" --limit 5
```

或通过 Python：

```python
import xqshare
xqshare.connect()
print(xqshare.xtdata.get_trading_dates("SH", count=5))
```

### 3.5.4 在 QmtQuant 中使用

项目中已通过 `env.py` 统一处理平台差异，**无需手动判断**：

```python
from env import xtdata  # 全平台统一入口

# 调用方式与 Windows 本地完全一致
data = xtdata.get_market_data_ex(
    stock_list=["000001.SZ"],
    period="1d",
    start_time="20240101",
    end_time="20241231",
)
```

> 📖 更多细节（如 Parallels 共享文件夹、虚拟环境隔离、常见问题排查）请参阅 `docs/mac-windows-bridge-design.md`。

---

# 第四章：快速上手：CLI 工具使用

本章介绍如何使用 QmtQuant 的 CLI 工具完成数据管理和策略回测。

## 4.1 数据管理 CLI（`dm_cli.py`）

`dm_cli.py` 是数据管理模块的命令行入口，支持数据同步、补充、校验、清理、市场监控等操作。

### 4.1.1 查看帮助与命令列表

```bash
python dm_cli.py --help
python dm_cli.py --list
```

### 4.1.2 数据同步

```bash
# 同步沪深300股票日线数据
python dm_cli.py sync --asset stock --sub kline --sector 沪深300 --period 1d

# 同步交易日历和标的信息
python dm_cli.py sync --asset stock --sub calendar,instrument

# 同步行业数据
python dm_cli.py sync --asset industry
```

### 4.1.3 数据下载（下载到 MiniQMT 本地）

```bash
# 增量下载沪深300日线数据
python dm_cli.py download --asset stock --sub kline --sector 沪深300 --period 1d

# 全量下载指定时间范围
python dm_cli.py download --asset stock --sub kline --sector 沪深300 --period 1d --mode full --start 20240101 --end 20241231

# 智能下载（自动检测缺口）
python dm_cli.py download --asset stock --sub kline --sector 沪深300 --period 1d --mode smart
```

### 4.1.4 数据校验与统计

```bash
# 查看本地缓存统计信息
python dm_cli.py stats

# 校验指定股票缓存完整性
python dm_cli.py validate --asset stock --sub kline --sector 沪深300 --period 1d

# 扫描数据缺口（只检测，不补充）
python dm_cli.py scan-gaps --asset stock --sub kline --sector 沪深300 --period 1d
```

### 4.1.5 清理缓存

```bash
# 清空指定股票的缓存
python dm_cli.py clear --symbol 600000.SH --period 1d

# 清空全部缓存
python dm_cli.py clear --all
```

---

## 4.2 回测 CLI（`bt_cli.py`）

`bt_cli.py` 是回测模块的命令行入口，支持加载 `.qmt` 配置文件运行回测、查看结果。

### 4.2.1 查看策略列表

```bash
python bt_cli.py list
```

### 4.2.2 运行回测

```bash
# 使用配置文件运行回测
python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt

# 覆盖回测时间范围
python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --start 20240101 --end 20241231

# 指定初始资金并初始化数据
python bt_cli.py run strategy/ZTSXP/ZTSXP.qmt --capital 500000 --init-data
```

### 4.2.3 查看回测结果

```bash
# 查看回测结果汇总
python bt_cli.py results

# 查看详细结果（最近10条）
python bt_cli.py results --detail --limit 10
```

---

## 4.3 配置文件（`.qmt` 文件）

`.qmt` 文件是 QmtQuant 的**工程配置文件**，本质上是 JSON 格式的文本文件，可以用任何文本编辑器直接编辑。

**典型配置示例**：

```json
{
  "strategy_file": "strategy/MACD/MACD.py",
  "start_date": "20240101",
  "end_date": "20241231",
  "initial_capital": 1000000,
  "stock_pool": ["000001.SZ", "600519.SH"],
  "period": "1m",
  "xt_client_path": "D:\\国金证券QMT交易端\\bin.x64\\XtItClient.exe",
  "xt_data_path": "D:\\国金证券QMT交易端\\userdata_mini"
}
```

---

## 4.4 "数据下载"与"数据同步"的区别

> **"数据下载"（`download`）** 的设计目标是服务于**系统内部**的回测功能。它调用 xtquant 的 `download_history_data` 函数，将数据下载到 MiniQMT 本地数据库，为策略回测引擎提供数据基础。回测过程中通过 `get_market_data_ex` 高速读取本地数据。

> **"数据同步"（`sync`）** 的核心在于将金融数据以独立、可见的 `.csv` 文件形式保存到本地缓存，支持**系统外部**的多元化数据应用。用户可以方便地将数据导入 Excel、Python、R 等进行复杂的统计建模或外部回测。

---

## 4.5 市场行情监控（`monitor` 子命令）

`monitor` 是 `dm_cli.py` 的市场行情监控分析子命令，每日收盘后执行，读取本地 Parquet 缓存生成 HTML 报告，**不发起任何网络请求**。

### 4.5.1 功能概览

报告包含三大模块，通过 Tab 切换展示：

| Tab | 模块 | 主要内容 |
|-----|------|---------|
| 🌐 市场全景 | 市场全景扫描 | 大盘指数涨跌、全市场涨跌分布、量能分析、新高新低统计 |
| 🚀 涨停监控 | 个股异动/涨停板监控 | 涨停股、跌停股、炸板股、量价异动股列表 |
| 🏭 行业轮动 | 行业板块轮动分析 | 行业涨跌排名、近5/10/20日累计涨跌、量能比、热点行业 |

### 4.5.2 基本用法

```bash
# 生成完整市场监控报告（自动取最新交易日）
python dm_cli.py monitor

# 指定分析日期
python dm_cli.py monitor --date 20260522

# 只生成行业轮动报告
python dm_cli.py monitor --type sector

# 只生成涨停板监控报告
python dm_cli.py monitor --type limit-up --date 20260522

# 指定股票池板块（影响全景扫描和涨停板监控的股票范围）
python dm_cli.py monitor --sector 沪深300

# 指定 HTML 输出路径
python dm_cli.py monitor --output /tmp/report.html
```

### 4.5.3 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--type` | `all` | 分析类型：`overview`（全景扫描）/ `limit-up`（涨停板）/ `sector`（行业轮动）/ `all`（全部） |
| `--date` | 自动 | 分析日期 `YYYYMMDD`，不指定则自动取本地缓存中最新的有效交易日 |
| `--sector` | `沪深A股` | 股票池板块，用于全景扫描和涨停板监控的股票范围 |
| `--classification` | `SW1` | 行业分类体系，可选 `SW1`/`SW2`/`SW3`/`CSRC1`/`CSRC2` |
| `--output` | `dashboard/market_report_{date}.html` | HTML 报告输出路径 |

### 4.5.4 行业分类体系（`--classification`）

行业轮动分析支持多种分类体系，通过 `--classification` 参数切换：

| 值 | 分类体系 | 行业数量 |
|----|---------|---------|
| `SW1` | 申万一级行业（默认） | 28 个 |
| `SW2` | 申万二级行业 | 104 个 |
| `SW3` | 申万三级行业 | 227 个 |
| `CSRC1` | 证监会一级行业 | 19 个 |
| `CSRC2` | 证监会二级行业 | 81 个 |

```bash
# 使用申万二级行业分类（104个行业）
python dm_cli.py monitor --type sector --classification SW2

# 使用证监会一级行业分类（19个行业）
python dm_cli.py monitor --type sector --classification CSRC1

# 全量报告 + 申万二级
python dm_cli.py monitor --classification SW2
```

> ⚠️ **注意**：切换到更细粒度的分类（如 SW2/SW3）时，分析耗时会显著增加，因为需要处理更多行业的成分股数据。

### 4.5.5 报告特性

- **离线可用**：纯 HTML + CSS + JavaScript，不依赖外部 CDN，生成后可离线查看
- **表格排序**：点击任意列头可排序
- **涨红跌绿**：数字颜色高亮
- **热点行业**：涨停股最多的前 3 个行业自动高亮标注 🔥
- **Tab 智能激活**：只运行部分模块时（如 `--type sector`），未运行的 Tab 自动置灰，直接激活有数据的 Tab
- **报告路径**：默认输出到 `dashboard/market_report_{YYYYMMDD}.html`

### 4.5.6 数据依赖

`monitor` 命令依赖以下本地 Parquet 缓存，请确保在运行前已完成对应数据的同步：

| 依赖数据 | 同步命令 | 用途 |
|---------|---------|------|
| 股票日线 K 线 | `python dm_cli.py sync --asset stock --sub kline --sector 沪深A股 --period 1d` | 全景扫描、涨停板监控、行业轮动 |
| 指数日线 K 线 | `python dm_cli.py sync --asset index --sub kline --period 1d` | 全景扫描大盘指数 |
| 合约信息 | `python dm_cli.py sync --asset stock --sub instrument` | 涨跌停价判断 |
| 行业成分股 | `python dm_cli.py sync --asset industry` | 行业轮动分析 |

---

## 4.6 Data API 服务（`data-api` 子命令）

`data-api` 是 `dm_cli.py` 的 HTTP API 服务子命令，基于 **FastAPI + uvicorn**，将本地 Parquet 缓存数据对外暴露为 REST 接口，供 `daily_stock_analysis` 等外部项目通过 HTTP 调用，实现数据复用。

### 4.6.1 功能概览

| 接口 | 说明 |
|------|------|
| `GET /health` | 健康检查，返回服务状态和缓存目录统计 |
| `GET /api/v1/kline` | K 线数据查询，支持 `standard`（默认）和 `raw` 两种返回格式 |
| `GET /api/v1/sector` | 板块成分股查询，不带参数时返回所有板块名称列表 |
| `GET /api/v1/instruments` | 合约基础信息查询，支持批量查询和分页 |
| `GET /api/v1/calendar` | 交易日历查询 |
| `GET /docs` | Swagger UI 在线文档 |

### 4.6.2 启动服务

```bash
# 默认启动（本机访问，端口 8765）
python dm_cli.py data-api

# 指定端口
python dm_cli.py data-api --port 9000

# 允许局域网内其他机器访问
python dm_cli.py data-api --host 0.0.0.0 --port 8765
```

启动后终端会打印缓存目录状态和已注册接口列表，按 `Ctrl+C` 优雅停止服务。

### 4.6.3 接口使用示例

**查询 K 线（standard 格式，与 `daily_stock_analysis` STANDARD_COLUMNS 兼容）：**

```bash
GET http://localhost:8765/api/v1/kline?symbol=600519.SH&period=1d&start=20240101&end=20241231
```

```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {"date": "2024-01-02", "open": 1700.0, "high": 1720.0, "low": 1695.0,
     "close": 1710.0, "volume": 12345.0, "amount": 2100000000.0, "pct_chg": 0.59}
  ]
}
```

**查询原始字段（raw 格式）：**

```bash
GET http://localhost:8765/api/v1/kline?symbol=600519.SH&period=1d&format=raw
```

**查询板块成分股：**

```bash
# 查询沪深300成分股
GET http://localhost:8765/api/v1/sector?name=沪深300

# 查询所有可用板块名称列表
GET http://localhost:8765/api/v1/sector
```

**查询合约基础信息：**

```bash
# 批量查询
GET http://localhost:8765/api/v1/instruments?symbols=600519.SH,000001.SZ

# 全量分页查询
GET http://localhost:8765/api/v1/instruments?page=1&page_size=500
```

**查询交易日历：**

```bash
GET http://localhost:8765/api/v1/calendar?start=20240101&end=20241231
```

### 4.6.4 统一响应格式

所有接口均返回统一的 JSON 格式：

```json
// 成功
{"code": 0, "message": "ok", "data": ...}

// 业务错误（如数据不存在）
{"code": 1, "message": "错误描述", "data": null}

// 依赖文件缺失（需先同步数据）
{"code": 503, "message": "文件不存在，请先执行 sync ...", "data": null}
```

所有响应头中包含 `X-QmtQuant-Version` 字段。

### 4.6.5 客户端 SDK

`data_api/client.py` 是配套的 Python 客户端 SDK，可复制到其他项目直接使用：

```python
from data_api.client import QmtQuantClient, QmtQuantConnectionError

client = QmtQuantClient(host="localhost", port=8765, timeout=10)

# 查询 K 线（返回 DataFrame，字段与 daily_stock_analysis STANDARD_COLUMNS 一致）
df = client.get_kline("600519.SH", "1d", "20240101", "20241231")

# 查询板块成分股（返回 [[symbol, name], ...]，与 DataFetcherManager.get_sector() 兼容）
members = client.get_sector("沪深300")

# 查询合约基础信息（返回 {symbol: {...}} 字典）
instruments = client.get_instruments(["600519.SH", "000001.SZ"])

# 查询交易日历（返回 ['YYYY-MM-DD', ...] 列表）
calendar = client.get_calendar("20240101", "20241231")

# 服务不可达时抛出 QmtQuantConnectionError
try:
    client.health()
except QmtQuantConnectionError as e:
    print(f"服务未启动：{e}")
```

### 4.6.6 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `127.0.0.1` | 监听地址（`0.0.0.0` 允许局域网访问） |
| `--port` | `8765` | 监听端口 |

### 4.6.7 依赖安装

```bash
pip install fastapi uvicorn[standard]
```

> 💡 **提示**：`data-api` 服务读取的是本地 Parquet 缓存（`~/.qmtquant/cache/`），请确保在启动服务前已通过 `sync` 命令完成所需数据的同步。

---

# 第十二章：策略编写初探：API与基本结构

如果说前几章是对 CLI 工具操作的指南，那么本章将深入到整个系统的核心——策略编写。本章旨在为开发者提供一个关于"qmt量化交易系统"策略框架的直观理解，并详细说明如何基于此框架，一步步构建属于自己的交易策略。我们将重点介绍策略文件的基本结构、核心回调函数，以及与框架交互的关键API。

---

## 策略框架是什么

对于每一位交易者而言，心中都有一套独特的交易逻辑。量化交易的本质，便是将这套逻辑转化为代码，让计算机去执行。然而，从零开始编写一套完整的交易程序是复杂且耗时的，需要处理数据获取、订单管理、风险控制、事件驱动等一系列繁琐的底层任务。

**策略框架**正是为了解决这一问题而生。可以将它理解为一个半成品的交易机器人，它已经为开发者搭建好了坚实的骨架，处理了所有与交易逻辑无关的技术细节。开发者只需要专注于策略本身，将交易思想填充到框架预留的接口中，即可快速构建出功能完备、稳定可靠的自动化交易策略。

为了贴近主流的量化实践和用户习惯，`QmtQuant` 定义了一套符合直觉的策略框架。它主要包含四个核心部分，分别对应策略生命周期中的不同阶段：

* **初始化 (`init`)**: 策略开始运行时，用于进行全局设置，仅执行一次。
* **盘前回调 (`on_pre_market`)**: 每个交易日开盘前，用于执行每日的准备工作。
* **主回调 (`on_bar`)**: 在盘中根据设定的频率被反复调用，是策略逻辑的核心。
* **盘后回调 (`on_post_market`)**: 每个交易日收盘后，用于执行当日的复盘和清理任务。

这四个部分均以函数的形式存在于策略文件中。框架会在特定的时间点自动调用这些函数，并将包含当前市场行情、账户资金、持仓情况等所有必要信息的 `context` 对象作为参数传递给它们。在函数中完成逻辑判断后，只需返回标准的交易指令（我们称之为"信号"），框架便会自动执行后续的下单操作。这种设计极大地简化了策略编写的复杂度，使开发者可以聚焦于策略逻辑本身，而非底层实现。

---

## 12.1 策略框架一览

一个策略文件本质上是一个标准的Python脚本，通过实现框架预定义的一系列函数来完成策略逻辑。以下是一个策略文件的最简化结构，它包含了所有主要的回调函数，可以作为开始编写新策略的模板。

```python
from typing import Dict, List

def init(stock_list, context):
    """
    策略初始化函数，在任务开始时仅执行一次。
    用于定义全局变量、加载外部数据等。
    """
    pass

def on_bar(context: Dict) -> List[Dict]:
    """
    策略核心逻辑，会被框架根据设定的频率反复调用。
    负责行情判断和生成交易信号。
    """
    signals = []
    return signals

def on_pre_market(context: Dict) -> List[Dict]:
    """
    盘前处理函数（可选）。
    在每日开盘前的指定时间点调用。
    """
    signals = []
    return signals

def on_post_market(context: Dict) -> List[Dict]:
    """
    盘后处理函数（可选）。
    在每日收盘后的指定时间点调用。
    """
    signals = []
    return signals
```

---

## 12.2 核心回调函数详解

框架通过在特定时机调用策略文件中的特定函数来驱动策略运行。开发者需要根据需求实现这些函数。为了更好地理解，可以参考我们提供的 `strategy/MACD.py` 策略示例文件，它展示了如何实现一个完整的策略。

### 12.2.1 `init(stock_list, context)` - 初始化函数

* **执行时机**：在整个回测或交易任务开始时，被框架**调用一次**。
* **核心作用**：用于执行策略的全局初始化任务，如设置参数、加载数据等。
* **参数说明**：
  * `stock_list` (list): 框架传入的股票池列表，例如 `['000001.SZ', '600000.SH']`。
  * `context` (dict): 一个包含初始化时刻上下文信息的字典。其内部详细结构如下：
    * **`__current_time__`** (dict): 包含当前时间信息的字典。
      * `timestamp`: (int) 标准Unix时间戳。
      * `datetime`: (str) 格式为 "YYYY-MM-DD HH:MM:SS" 的日期时间字符串。
      * `date`: (str) 格式为 "YYYY-MM-DD" 的日期字符串。
      * `time`: (str) 格式为 "HH:MM:SS" 的时间字符串。
    * **`__account__`** (dict): 包含账户资金信息的字典。
      * `account_type`: (str) 账户类型 (例如, 'STOCK')。
      * `account_id`: (str) 账户ID。
      * `cash`: (float) 当前可用资金。
      * `frozen_cash`: (float) 冻结资金。
      * `market_value`: (float) 持仓市值。
      * `total_asset`: (float) 总资产。
      * `benchmark`: (str) 基准指数代码。
    * **`__positions__`** (dict): 包含持仓信息的字典，在初始化时通常为空 `{}`。
    * **`__framework__`** (object): 框架核心类的实例。它包含了最全面的框架信息和功能接口。如果其他上下文参数不包含所需信息，可以尝试通过此对象获取。

### 12.2.2 `on_bar(context)` - 策略主逻辑函数

* **执行时机**：根据主界面"运行驱动区"设置的**触发方式**，被框架反复、高频地调用。
* **核心作用**：这是实现交易策略核心逻辑的地方，包括行情判断、信号生成、下单等。
* **参数说明**：
  * `context` (dict): 包含当前时间点所有可用信息的字典，其结构为：
    * **`__current_time__`** (dict): 包含当前时间信息的字典。
      * `timestamp`: (int) 标准Unix时间戳。
      * `datetime`: (str) 格式为 "YYYY-MM-DD HH:MM:SS" 的日期时间字符串。
      * `date`: (str) 格式为 "YYYY-MM-DD" 的日期字符串。
      * `time`: (str) 格式为 "HH:MM:SS" 的时间字符串。
    * **`__account__`** (dict): 包含账户资金信息的字典。
      * `account_type`: (str) 账户类型。
      * `account_id`: (str) 账户ID。
      * `cash`: (float) 当前可用资金。
      * `frozen_cash`: (float) 冻结资金。
      * `market_value`: (float) 持仓市值。
      * `total_asset`: (float) 总资产。
      * `benchmark`: (str) 基准指数代码。
    * **`__positions__`** (dict): 包含当前持仓信息的字典。其结构为 `{股票代码: 持仓详情}`。持仓详情是一个字典，包含了该股票的详细持仓信息，其内部字段如下：
      * `account_type`: (int) 账户类型。
      * `account_id`: (str) 账户ID。
      * `stock_code`: (str) 股票代码。
      * `volume`: (int) 持仓数量。
      * `can_use_volume`: (int) 可用数量（可卖出数量）。
      * `open_price`: (float) 当日开盘价。
      * `market_value`: (float) 持仓市值。
      * `frozen_volume`: (int) 冻结数量。
      * `on_road_volume`: (int) 在途数量。
      * `yesterday_volume`: (int) 昨日持仓数量。
      * `avg_price`: (float) 持仓成本价。
      * `current_price`: (float) 当前市价。
      * `direction`: (int) 持仓方向。
      * `profit`: (float) 持仓浮动盈亏。
      * `profit_ratio`: (float) 持仓盈亏率。
    * **`__framework__`** (object): 框架核心类的实例。它包含了最全面的框架信息和功能接口。如果其他上下文参数不包含所需信息，可以尝试通过此对象获取。
    * **`[股票代码]`** (pandas.Series): 以股票代码（如`'000001.SZ'`）为键，值为一个Pandas Series对象，包含了该股票在当前时间点的所有行情字段（如`open`, `high`, `low`, `close`, `volume`等）。
* **返回值**:
  * 该函数需要返回一个**交易信号列表** (`List[Dict]`)。框架在收到返回的列表后，会自动解析其中的每一条指令，并调用底层的交易接口去执行。如果列表为空，则框架认为当前时间点无任何操作。
  * 一个标准的交易信号字典包含以下键值对：

| 键 (Key) | 类型 (Type) | 必填 | 说明 |
|---|---|---|---|
| `code` | str | 是 | 股票代码，必须是标准的QMT格式，例如 `'000001.SZ'` 或 `'600036.SH'`。|
| `action` | str | 是 | 交易动作。可选值为 'buy' (买入) 或 'sell' (卖出)。|
| `price` | float | 是 | 交易价格。|
| `volume` | int | 是 | 交易数量，必须是100的整数倍。|
| `reason` | str | 否 | 交易原因或备注。此信息会显示在日志和交易记录中。|
| `timestamp`| int | 否 | 信号生成时的时间戳。 |

  * 关于信号字典的更详细说明，请参考 **12.7 交易信号详解**。

### 12.2.3 `on_pre_market(context)` - 盘前处理函数（可选）

* **执行时机**：在每个交易日的指定盘前时间点（如09:00）被调用一次。该功能需要在主界面"盘前盘后触发设置"中勾选"触发盘前回调"才会生效。
* **参数 `context`**：其结构与 `on_bar` 函数的 `context` **完全相同**。它包含了**当天第一个行情数据点**的所有信息，包括账户、持仓、以及股票池内所有股票在该时刻的行情数据。
* **返回值**：与 `on_bar` 类似，返回一个交易信号列表 (`List[Dict]`)。
* **常见用途**：
  * 每日选股、计算因子。
  * 重置当日的交易状态或计数器。
  * 提前下达一些集合竞价阶段的预埋单。

### 12.2.4 `on_post_market(context)` - 盘后处理函数（可选）

* **执行时机**：在每个交易日的指定盘后时间点（如15:30）被调用一次。该功能需要在主界面"盘前盘后触发设置"中勾选"触发盘后回调"才会生效。
* **参数 `context`**：其结构与 `on_bar` 函数的 `context` **完全相同**。它包含了**当天最后一个行情数据点**的所有信息，包括账户、持仓、以及股票池内所有股票在该时刻的行情数据。
* **返回值**：与 `on_bar` 类似，返回一个交易信号列表 (`List[Dict]`)。
* **常见用途**：
  * 当日交易复盘、业绩归因分析。
  * 保存当日的策略状态或数据到本地文件。
  * 清理当日持仓，或为下一个交易日做准备。

---

## 12.3 获取时间数据

在策略中，所有时间相关的信息都储存在 `context['__current_time__']` 这个字典中。通过访问它，可以获取到策略当前执行点的精确时间。

* `context['__current_time__']['timestamp']`: 返回一个整数形式的Unix时间戳。
* `context['__current_time__']['datetime']`: 返回 `YYYY-MM-DD HH:MM:SS` 格式的字符串，最常用。
* `context['__current_time__']['date']`: 返回 `YYYY-MM-DD` 格式的日期字符串。
* `context['__current_time__']['time']`: 返回 `HH:MM:SS` 格式的时间字符串。

**示例：实现简单的择时逻辑**

```python
def on_bar(context: Dict) -> List[Dict]:
    time_info = context['__current_time__']
  
    # 获取当前时间字符串，如 '09:31:00'
    current_time = time_info['time']
  
    # 简单的交易时间控制：只在上午10点后、下午2点半前进行交易判断
    if "10:00:00" < current_time < "14:30:00":
        # 在这里编写主要的策略逻辑...
        print("处于交易时间段，执行策略。")
    else:
        # 非交易时间段，不执行任何操作
        print("非交易时间段，跳过。")
  
    return []
```

---

## 12.4 获取账户数据

账户的资金状况信息储存在 `context['__account__']` 字典中，它提供了账户资产的实时快照。

* `context['__account__']['cash']`: (float) 当前可用于交易的现金。
* `context['__account__']['market_value']`: (float) 所有持仓按当前市价计算的总市值。
* `context['__account__']['total_asset']`: (float) 总资产，即 `cash` + `market_value`。
* `context['__account__']['frozen_cash']`: (float) 因挂单而冻结的资金。

**示例：根据资金动态计算买入量**

```python
def on_bar(context: Dict) -> List[Dict]:
    account = context['__account__']
  
    # 获取当前可用资金
    available_cash = account['cash']
  
    # 设定一个目标仓位：使用当前可用资金的20%
    cash_to_use = available_cash * 0.2
  
    # 获取 '000001.SZ' 的当前价格
    stock_data = context.get('000001.SZ')
    if stock_data is not None and not stock_data.empty:
        stock_price = stock_data['close']
  
        # 计算理论上可以买入多少股，并向下取整到100的倍数
        if stock_price > 0:
            volume_to_buy = int(cash_to_use / stock_price / 100) * 100
            if volume_to_buy > 0:
                print(f"资金充足，计划以 {stock_price} 元的价格买入 {volume_to_buy} 股 000001.SZ")
                # 此处可以构建并返回一个买入信号
    
    return []
```

---

## 12.5 获取持仓数据

持仓信息 `context['__positions__']` 是一个字典，键为股票代码，值为该股票的详细持仓信息字典。这使得检查特定持仓、获取持仓细节变得非常方便。

**示例：实现持仓股票的止盈止损**

```python
def on_bar(context: Dict) -> List[Dict]:
    positions = context['__positions__']
    signals = []
  
    # 检查是否持有 '600519.SH' (贵州茅台)
    if '600519.SH' in positions:
        # 获取该持仓的详细信息
        pos_info = positions['600519.SH']
  
        volume = pos_info['volume']
        profit_ratio = pos_info['profit_ratio'] # 获取持仓盈亏率
  
        print(f"持有 {volume} 股 600519.SH，当前盈利 {profit_ratio*100:.2f}%")
  
        # 止盈逻辑：如果盈利超过10%，就全部卖出
        if profit_ratio > 0.10:
            sell_signal = {
                'action': 'sell',
                'code': '600519.SH',
                'volume': volume, # 卖出全部持仓
                'remark': '盈利超过10%，止盈'
            }
            signals.append(sell_signal)
  
        # 止损逻辑：如果亏损超过5%，就全部卖出
        elif profit_ratio < -0.05:
            sell_signal = {
                'action': 'sell',
                'code': '600519.SH',
                'volume': volume, # 卖出全部持仓
                'remark': '亏损超过5%，止损'
            }
            signals.append(sell_signal)
  
    return signals
```

---

## 12.6 获取当前运行配置

在某些复杂的策略场景中，可能需要在策略逻辑内部获取在GUI界面上配置的参数，例如获取设置的基准合约代码，或者根据不同的手续费配置调整交易行为。

这些配置信息可以通过 `context` 中的 `__framework__` 对象进行访问。

**示例：在策略中获取基准合约和手续费配置**

```python
def init(stock_list, context):
    # 从框架对象中获取配置实例
    config = context['__framework__'].config

    # 读取回测配置中的 'benchmark' 参数
    benchmark_code = config.get_config('backtest.benchmark')
    print(f"当前配置的基准合约为: {benchmark_code}")

    # 读取交易成本中的佣金比例
    commission_rate = config.get_config('backtest.trade_cost.commission_rate')
    print(f"当前配置的佣金比例为: {commission_rate}")
```

---

## 12.7 交易信号详解

交易信号是策略与交易执行模块沟通的唯一方式。它是一个包含了所有交易必要信息的Python字典。`on_bar`、`on_pre_market`、`on_post_market`的返回值以及`__framework__.trade()`的参数都是交易信号。

一个标准的交易信号字典包含以下键值对：


| 键 (Key)    | 类型 (Type) | 必填 | 说明                                                                |
| ----------- | ----------- | ---- | ------------------------------------------------------------------- |
| `code`      | str         | 是   | 股票代码，必须是标准的QMT格式，例如`'000001.SZ'` 或 `'600036.SH'`。 |
| `action`    | str         | 是   | 交易动作。可选值为 'buy' (买入) 或 'sell' (卖出)。                  |
| `price`     | float       | 是   | 交易价格。                                                          |
| `volume`    | int         | 是   | 交易数量，必须是100的整数倍。                                       |
| `reason`    | str         | 否   | 交易原因或备注。此信息会显示在日志和交易记录中。                    |
| `timestamp` | int         | 否   | 信号生成时的时间戳。                                                |

**示例：**

```python
# 以10.5元的价格买入100股平安银行
signal_1 = {
    'code': '000001.SZ',
    'action': 'buy',
    'price': 10.5,
    'volume': 100,
    'reason': 'MACD金叉买入'
}

# 以18.5元的价格卖出200股贵州茅台
signal_2 = {
    'code': '600519.SH',
    'action': 'sell',
    'price': 18.50,
    'volume': 200,
    'reason': '达到止盈位卖出'
}
```

## 12.8 在策略中使用日志

为了方便调试和监控策略的内部状态，可以在策略代码中直接调用日志输出功能，将信息发送到qmt量化交易系统的日志系统（包括界面和文件）。

**核心机制**：框架已经对Python内置的 `logging` 模块进行了配置。因此，开发者无需关心日志的底层实现，只需在策略代码中导入 `logging` 模块，然后直接调用其标准函数即可。

**使用方法：**

1. 在策略文件顶部添加 `import logging`。
2. 在代码中调用 `logging.info()`, `logging.warning()`, `logging.error()` 等函数。

日志级别与界面上显示的颜色直接对应：

* **普通信息 (INFO)**: 使用 `logging.info("进入长仓条件判断")` 输出常规的流程信息或变量状态。这对应界面上的 **白色** 文本。
* **调试信息 (DEBUG)**: 如果需要输出更详细的、仅在调试时关心的变量值或中间计算结果，可以使用 `logging.debug(f"当前ATR值: {atr_value}")`。这对应界面上的 **浅紫色** 文本。（注意：默认配置下，DEBUG级别的日志可能不会显示，需在设置中调整）
* **警告信息 (WARNING)**: 当策略遇到一些非致命但需要注意的情况时，比如某个数据获取失败但有备用方案，可以使用 `logging.warning("无法获取最新行情，使用上一周期数据代替")`。这对应界面上的 **橙色** 文本，比较醒目。
* **错误信息 (ERROR)**: 当策略发生严重错误，可能导致后续逻辑无法正常执行时，应使用 `logging.error("计算指标时出现除零错误")` 。这对应界面上最醒目的 **红色** 文本，强烈提示需要检查问题。

**示例：**

```python
import logging
from typing import Dict, List

def on_bar(context: Dict) -> List[Dict]:
    # 检查账户现金
    cash = context['__account__']['cash']
    logging.info(f"当前可用资金: {cash}")

    if cash < 10000:
        logging.warning("可用资金不足1万元，跳过本次交易机会。")
        return []
  
    # ...后续策略逻辑...
    try:
        # 可能会出错的代码
        risky_value = 1 / 0
    except Exception as e:
        logging.error(f"计算风险值时发生严重错误: {e}", exc_info=True) # exc_info=True会记录完整的错误堆栈

    return []
```

### 如何输出醒目的内容？

如果希望某条日志信息在界面上特别突出，最直接的方式是使用 `logging.warning()` 或 `logging.error()`。`ERROR` 级别（红色）最为醒目，通常用于指示发生了必须处理的问题。`WARNING` 级别（橙色）也比较突出，适合用于提示潜在风险或需要关注的状态。请根据信息的重要性和紧急程度，审慎选择合适的级别进行输出。

---

## 12.9 策略工具箱：`utils` 模块详解

为了进一步简化策略开发，`QmtQuant` 提供了 `utils` 工具包，其中包含了一系列高效实用的辅助函数。这些工具涵盖了时间判断、交易计算、数据获取等多个方面，能够帮助开发者快速实现复杂的逻辑，避免重复造轮子。

要使用这些工具，只需在策略文件的顶部从 `utils` 包导入所需的函数即可。

```python
# 在策略文件顶部导入工具函数
from utils import (
    calculate_max_buy_volume,
    generate_signal,
    moving_avg,
)
```

### 12.9.1 时间工具 


#### `is_trade_time()`

* **功能**：判断当前时间是否处于A股的常规交易时间段内（09:30-11:30, 13:00-15:00）。
* **返回值**：`bool`，是则返回 `True`，否则返回 `False`。
* **使用场景**：确保交易逻辑只在开盘时段执行。

**示例：**

```python
def on_bar(context: Dict) -> List[Dict]:
    if not tools.is_trade_time():
        return [] # 非交易时间，直接返回

    # ... 在此编写交易时间内的策略逻辑 ...
    logging.info("交易时间内，执行策略。")
    return []
```

#### `is_trade_day(date_str)`

* **功能**：判断指定日期是否为A股的交易日（会剔除周末和法定节假日）。
* **参数**：
  * `date_str` (str, 可选): `YYYY-MM-DD` 格式的日期字符串。如果留空，则默认判断当天。
* **返回值**：`bool`，是交易日则返回 `True`，否则返回 `False`。

**示例：**

```python
# 判断2024年10月1日是否是交易日
is_trading = tools.is_trade_day("2024-10-01") 
print(f"2024-10-01 是交易日吗? {'是' if is_trading else '否'}")

# 判断今天是否是交易日
is_today_trading = tools.is_trade_day()
print(f"今天是交易日吗? {'是' if is_today_trading else '否'}")
```

#### `get_trade_days_count(start_date, end_date)`

* **功能**：计算两个日期之间的A股交易日天数。
* **参数**：
  * `start_date` (str): `YYYY-MM-DD` 格式的开始日期。
  * `end_date` (str): `YYYY-MM-DD` 格式的结束日期。
* **返回值**：`int`，两个日期之间的交易日总数。

**示例：**

```python
# 计算2024年全年的交易日天数
days = tools.get_trade_days_count("2024-01-01", "2024-12-31")
print(f"2024年共有 {days} 个交易日。")
```

### 12.9.2 交易辅助函数

#### `calculate_max_buy_volume(data, stock_code, price, cash_ratio)`

* **功能**：一个非常实用的函数，用于根据可用资金和股价，计算出理论上可以买入的最大股票数量（会自动向下取整到100的倍数）。
* **参数**：
  * `data` (dict): 即策略回调函数中的 `context` 对象。
  * `stock_code` (str): 计划买入的股票代码。
  * `price` (float): 计划买入的价格。
  * `cash_ratio` (float, 可选): 计划使用的资金比例，默认为 `1.0` (即全部可用资金)。
* **返回值**：`int`，可以买入的最大股数。

**示例：**

```python
def on_bar(context: Dict) -> List[Dict]:
    # 计划用50%的资金买入平安银行
    stock_to_buy = '000001.SZ'
    current_price = context.get(stock_to_buy)['close'] # 获取当前价

    # 计算最多能买多少股
    max_volume = calculate_max_buy_volume(context, stock_to_buy, current_price, cash_ratio=0.5)

    if max_volume > 0:
        logging.info(f"资金足够，计划以 {current_price} 的价格买入 {max_volume} 股 {stock_to_buy}")
        # ...后续可以生成并返回交易信号
  
    return []
```

#### `generate_signal(data, stock_code, price, ratio, action, reason)`

* **功能**：高级信号生成函数。对于买入操作，它会自动计算最大可买股数；对于卖出操作，它会自动计算最大可卖股数。极大简化了信号的创建过程。
* **参数**：
  * `data` (dict): 即 `context` 对象。
  * `stock_code` (str): 交易的股票代码。
  * `price` (float): 交易价格。
  * `ratio` (float): 比例。当 `action` 为 `'buy'` 时，这是资金使用比例；当 `action` 为 `'sell'` 时，这是持仓卖出比例。
  * `action` (str): 交易动作，`'buy'` 或 `'sell'`。
  * `reason` (str, 可选): 交易原因。
* **返回值**：`List[Dict]`，一个包含单个交易信号的列表，如果条件不满足（如无钱可买或无仓可卖），则返回空列表。

**示例：**

```python
def on_bar(context: Dict) -> List[Dict]:
    signals = []
  
    # 假设 is_rsi_low 和 is_rsi_high 是已经计算好的布尔值
    is_rsi_low = True 
    is_rsi_high = True

    # 1. 如果RSI指标小于30，使用30%的资金买入平安银行
    if is_rsi_low and '000001.SZ' in context:
        # 只需指定买入比例，函数会自动计算股数
        buy_signals = generate_signal(context, '000001.SZ', price=context.get('000001.SZ')['close'], ratio=0.3, action='buy', reason='RSI < 30')
        signals.extend(buy_signals)

    # 2. 如果持有茅台，且RSI指标大于70，卖出50%的仓位
    if '600519.SH' in context['__positions__'] and is_rsi_high:
        # 只需指定卖出比例，函数会自动计算股数
        sell_signals = generate_signal(context, '600519.SH', price=context.get('600519.SH')['close'], ratio=0.5, action='sell', reason='RSI > 70')
        signals.extend(sell_signals)

    return signals
```

### 12.9.3 数据获取与处理

#### `moving_avg(symbol_list, fields, bar_count, fre_step, current_time=None, skip_paused=False, fq='pre', force_download=False)`

*   **功能**：**（核心功能）** 获取指定证券的历史K线数据，是计算各种技术指标的基础。

*   **入口参数 (Input)**:
    *   `symbol_list` (list): 证券代码列表。必须是包含标准QMT格式（如`'600000.SH'`）的字符串列表。
    *   `fields` (list): 希望获取的行情字段列表。常用的字段包括 `'time'`, `'open'`, `'high'`, `'low'`, `'close'`, `'volume'` (成交量), `'amount'` (成交额)。返回的DataFrame将包含这些列。
    *   `bar_count` (int): 希望获取的K线数量。例如，`bar_count=30` 和 `fre_step='1d'` 将获取过去30个交易日的日K线数据。
    *   `fre_step` (str): K线周期。支持 `'1m'`, `'5m'`, `'15m'`, `'30m'`, `'60m'` 等分钟线周期，以及 `'1d'` (日线), `'1w'` (周线), `'1mon'` (月线)。
    *   `current_time` (str, 可选): 获取历史数据的结束时间点，格式为 `'YYYYMMDDHHMMSS'`。如果设为 `None` 或不提供，则数据截止到当前最新时间。这对于回测中模拟特定时间点的情景非常重要。
    *   `skip_paused` (bool, 可选): 是否跳过停牌日。默认为 `False`。如果设为 `True`，返回的 `bar_count` 根K线将不包含该股票的停牌日，K线是连续的。
    *   `fq` (str, 可选): 复权类型。默认为 `'pre'` (前复权)。可选值为 `'back'` (后复权) 或 `'none'` (不复权)。
    *   `force_download` (bool, 可选): 是否强制从远程服务器下载新数据，忽略本地缓存。默认为 `False`。在进行数据补全或怀疑本地数据有误时，可设为 `True`。

*   **输出参数 (Output)**:
    *   **返回值**: 一个Python字典。
    *   **字典结构**:
        *   **键 (Key)**: 股票代码字符串 (e.g., `'000001.SZ'`)。
        *   **值 (Value)**: 一个`pandas.DataFrame`对象，或者在获取失败时为`None`。
    *   **DataFrame结构**:
        *   **索引 (Index)**: 默认的整数索引。
        *   **列 (Columns)**: 与输入的 `fields` 参数完全对应。例如，如果 `fields=['time', 'open', 'close']`，DataFrame就会有这三列。`time`列是 `datetime` 对象，方便进行时间序列分析。

**示例：在 `init` 中预加载数据，在 `on_bar` 中计算5日均线**

```python
import pandas as pd
import logging
from utils import moving_avg

# 在全局范围定义一个缓存，用于存储计算好的指标
g = {'sma5': {}}

def init(stock_list, context):
    """
    在初始化时，一次性获取所有股票过去30天的日线数据，用于后续计算。
    """
    logging.info("开始获取历史数据用于初始化...")
    history_data = moving_avg(
        symbol_list=stock_list,
        fields=['time', 'open', 'close'],
        bar_count=30,
        fre_step='1d'
    )
  
    for stock in stock_list:
        df = history_data.get(stock)
        if df is not None and not df.empty:
            # 计算5日均线并存入全局缓存
            g['sma5'][stock] = df['close'].rolling(window=5).mean().iloc[-1]
            logging.info(f"{stock} 的初始5日均线值为: {g['sma5'][stock]}")

def on_bar(context: Dict) -> List[Dict]:
    signals = []
    # 假设股票池里有 '000001.SZ'
    stock_code = '000001.SZ'
    if stock_code in context:
        current_price = context.get(stock_code)['close']
        sma5_value = g['sma5'].get(stock_code)

        if sma5_value and current_price > sma5_value:
            logging.info(f"{stock_code} 当前价格上穿5日线，产生买入信号。")
            # 此处可构建买入信号
          
    # 注意：在实盘中，需要每日更新缓存的指标值，可以在on_pre_market中实现
    return signals
```
