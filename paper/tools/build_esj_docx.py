"""Build the ESJ (Emerging Science Journal) Word manuscript from the journal template.

Usage:  python -P paper/tools/build_esj_docx.py "paper/Article Template.docx" paper/manuscript_ESJ.docx

The template's front matter (title, authors, affiliations, abstract box, header, footnote) is edited
in place; the body is rebuilt by cloning the template's own prototype paragraphs/tables so every
style matches the journal's. Equations are native Word math (OMML).

Inline markup in content strings:
  {b|text} bold   {i|text} italic   {sub|text} subscript   {sup|text} superscript
  {R|ID: text} red result placeholder   {T|text} blue authoring TODO   {c|key1,key2} citation
Once co-authors start editing the .docx by hand, treat the .docx as the master and stop regenerating.
"""
import copy
import re
import sys
import zipfile
import shutil
import os
import tempfile

import docx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import results_wp3 as RW  # noqa: E402  (every result number comes from experiments/analysis)
from docx.oxml.ns import qn
from docx.shared import Mm
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
RED, BLUE = "C00000", "0070C0"

# ----------------------------------------------------------------------------------------------
# Citations and references
# ----------------------------------------------------------------------------------------------
# Verified 2026-11-23 against: arXiv API, Crossref, OpenReview, PMLR, IACR ePrint, Semantic Scholar, and the live pages.
MANUAL = " {R|verify manually: site blocks automated access}"
REFS = {
 "ballandies2023depin": "Ballandies, M. C., Wang, H., Law, A. C. C., Yang, J. C., Gösken, C., & Andrew, M. (2023). A taxonomy for blockchain-based decentralized physical infrastructure networks (DePIN). 2023 IEEE 9th World Forum on Internet of Things (WF-IoT), 1–6. doi:10.1109/WF-IoT58464.2023.10539514.",
 "lin2024depin": "Lin, Z., Wang, T., Shi, L., Zhang, S., & Cao, B. (2025). Decentralized physical infrastructure networks (DePIN): Challenges and opportunities. IEEE Network, 39(2), 91–99. doi:10.1109/MNET.2024.3487924.",
 "render2023": "Render Foundation. (n.d.). Render whitepaper. Available online: https://renderfoundation.com/whitepaper (accessed on November 23, 2026).",
 "akash2026": "Akash Network. (n.d.). Core concepts. Akash documentation. Available online: https://akash.network/docs/getting-started/core-concepts/ (accessed on October 16, 2026)." + MANUAL,
 "ionet2026": "io.net. (n.d.). FAQ: How does decentralized GPU compute work? Available online: https://io.net/p/faq-how-does-decentralized-gpu-compute-work (accessed on November 23, 2026).",
 "comfyui": "Comfy-Org. (2026). ComfyUI (commit 8b25bbc) [Computer software]. GitHub. Available online: https://github.com/Comfy-Org/ComfyUI (accessed on November 23, 2026). {T|update to the pinned experiment commit}",
 "cai2025substitution": "Cai, W., Shi, T., Zhao, X., & Song, D. (2025). Are you getting what you pay for? Auditing model substitution in LLM APIs. arXiv preprint arXiv:2504.04715. doi:10.48550/arXiv.2504.04715.",
 "gao2025met": "Gao, I., Liang, P., & Guestrin, C. (2025). Model equality testing: Which model is this API serving? The Thirteenth International Conference on Learning Representations (ICLR 2025), Singapore.",
 "diffusers_repro": "Hugging Face. (n.d.). Create reproducible pipelines. Diffusers documentation. Available online: https://huggingface.co/docs/diffusers/main/using-diffusers/reproducibility (accessed on November 23, 2026).",
 "yuan2025nondeterminism": "Yuan, J., Li, H., Ding, X., Xie, W., Li, Y.-J., Zhao, W., Wan, K., Shi, J., Hu, X., & Liu, Z. (2025). Understanding and mitigating numerical sources of nondeterminism in LLM inference. Advances in Neural Information Processing Systems 38 (NeurIPS 2025), 188045–188077. doi:10.52202/085713-5653.",
 "yao2026tao": "Yao, J., Su, H., Liao, T., Cheng, Z., Zhang, H., Wang, X., & Viswanath, P. (2026). TAO: Tolerance-aware optimistic verification for floating-point neural networks. Proceedings of the 21st European Conference on Computer Systems (EuroSys ’26), 1515–1532. doi:10.1145/3767295.3803612.",
 "nicheimage_repo": "SocialTensor. (2025). NicheImage: Bittensor subnet 23 (commit a4a2461) [Computer software]. GitHub. Available online: https://github.com/SocialTensor/SocialTensorSubnet (accessed on November 23, 2026).",
 "wombo_repo": "WOMBO. (2024). wombo-bittensor-subnet: Bittensor subnet 30 (commit 91b66fe, archived) [Computer software]. GitHub. Available online: https://github.com/womboai/wombo-bittensor-subnet (accessed on November 23, 2026).",
 "kim2024reproducibility": "Kim, E., Isozaki, I., Sirkin, N., & Robson, M. (2023). Generative artificial intelligence reproducibility and consensus. arXiv preprint arXiv:2307.01898. doi:10.48550/arXiv.2307.01898.",
 "gennaro2010vc": "Gennaro, R., Gentry, C., & Parno, B. (2010). Non-interactive verifiable computing: Outsourcing computation to untrusted workers. Advances in Cryptology – CRYPTO 2010, Lecture Notes in Computer Science, 6223, 465–482. doi:10.1007/978-3-642-14623-7_25.",
 "chen2024zkml": "Chen, B.-J., Waiwitlikhit, S., Stoica, I., & Kang, D. (2024). ZKML: An optimizing system for ML inference in zero-knowledge proofs. Proceedings of the Nineteenth European Conference on Computer Systems (EuroSys ’24), 560–574. doi:10.1145/3627703.3650088.",
 "ong2025toploc": "Ong, J. M., Di Ferrante, M., Pazdera, A., Garner, R., Jaghouar, S., Basra, M., Ryabinin, M., & Hagemann, J. (2025). TOPLOC: A locality sensitive hashing scheme for trustless verifiable inference. Proceedings of the 42nd International Conference on Machine Learning (ICML 2025), PMLR 267, 47196–47211.",
 "wang2025verillm": "Wang, K., Zhao, Z., Song, X., Li, Z., Xia, L., Tong, C., Shi, B., Qu, W., Yang, E., & Ai, L. (2025). VeriLLM: A lightweight framework for publicly verifiable decentralized inference. arXiv preprint arXiv:2509.24257. doi:10.48550/arXiv.2509.24257.",
 "arun2025verde": "Arun, A., St. Arnaud, A., Titov, A., Wilcox, B., Kolobaric, V., Brinkmann, M., Ersoy, O., Fielding, B., & Bonneau, J. (2025). Verde: Verification via refereed delegation for machine learning programs. arXiv preprint arXiv:2502.19405. doi:10.48550/arXiv.2502.19405.",
 "alves2026eigenai": "Ribeiro Alves, D., Patankar, V., Pereira, M., Stephens, J., Vaziri, N., & Kannan, S. (2026). EigenAI: Deterministic inference, verifiable results. arXiv preprint arXiv:2602.00182. doi:10.48550/arXiv.2602.00182.",
 "he2025nondeterminism": "He, H., & Thinking Machines Lab. (2025). Defeating nondeterminism in LLM inference. Thinking Machines Lab: Connectionism, September 10, 2025. Available online: https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/ (accessed on November 23, 2026).",
 "hawkeye2026": "Badash, E., Boneh, D., Komargodski, I., & Srivastava, M. (2026). Hawkeye: Reproducing GPU-level non-determinism. Proceedings of Machine Learning and Systems (MLSys 2026). arXiv:2603.20421. {R|add proceedings pages and DOI when published}",
 "zhang2024posp": "Zhang, Y., Wang, S., Tan, S., Liu, X., Moallemi, C. C., & Popa, R. A. (2024). Proof of sampling: A Nash equilibrium-based verification protocol for decentralized systems. arXiv preprint arXiv:2405.00295. doi:10.48550/arXiv.2405.00295.",
 "du2023edgemarket": "Du, Y., Wang, Z., Li, J., Shi, L., Jayakody, D. N. K., Chen, Q., Chen, W., & Han, Z. (2023). Blockchain-aided edge computing market: Smart contract and consensus mechanisms. IEEE Transactions on Mobile Computing, 22(6), 3193–3208. doi:10.1109/TMC.2021.3140080.",
 "fan2021hybrid": "Fan, S., Zhang, H., Zeng, Y., & Cai, W. (2021). Hybrid blockchain-based resource trading system for federated learning in edge computing. IEEE Internet of Things Journal, 8(4), 2252–2264. doi:10.1109/JIOT.2020.3028101.",
 "wang2024stackelberg": "Wang, D., Du, X., Zhang, H., & Wang, Q. (2024). Blockchain enabled credible computing resource sharing: A multi-leader multi-follower Stackelberg game approach. IEEE Transactions on Vehicular Technology, 73(9), 13839–13852. doi:10.1109/TVT.2024.3386331.",
 "yang2019survey": "Yang, R., Yu, F. R., Si, P., Yang, Z., & Zhang, Y. (2019). Integrated blockchain and edge computing systems: A survey, some research issues and challenges. IEEE Communications Surveys & Tutorials, 21(2), 1508–1532. doi:10.1109/COMST.2019.2894727.",
 "asgaonkar2018escrow": "Asgaonkar, A., & Krishnamachari, B. (2019). Solving the buyer and seller’s dilemma: A dual-deposit escrow smart contract for provably cheat-proof delivery and payment for a digital good without a trusted mediator. 2019 IEEE International Conference on Blockchain and Cryptocurrency (ICBC), 262–267. doi:10.1109/BLOC.2019.8751482.",
 "yakovenko2018solana": "Yakovenko, A. (2018). Solana: A new architecture for a high performance blockchain (v0.8.13). Available online: https://solana.com/solana-whitepaper.pdf (accessed on October 16, 2026)." + MANUAL,
 "solana_fees": "Solana Foundation. (n.d.). Fees. Solana documentation. Available online: https://solana.com/docs/core/fees (accessed on October 16, 2026)." + MANUAL,
 "zhang2018lpips": "Zhang, R., Isola, P., Efros, A. A., Shechtman, E., & Wang, O. (2018). The unreasonable effectiveness of deep features as a perceptual metric. 2018 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR), 586–595. doi:10.1109/CVPR.2018.00068.",
 "yu2022parti": "Yu, J., Xu, Y., Koh, J. Y., Luong, T., Baid, G., Wang, Z., Vasudevan, V., Ku, A., Yang, Y., Ayan, B. K., Hutchinson, B., Han, W., Parekh, Z., Li, X., Zhang, H., Baldridge, J., & Wu, Y. (2022). Scaling autoregressive models for content-rich text-to-image generation. Transactions on Machine Learning Research. Available online: https://openreview.net/forum?id=AFDcYJKhND (accessed on November 24, 2026).",
 "oquab2023dinov2": "Oquab, M., Darcet, T., Moutakanni, T., Vo, H. V., Szafraniec, M., Khalidov, V., Fernandez, P., Haziza, D., Massa, F., El-Nouby, A., Assran, M., Ballas, N., Galuba, W., Howes, R., Huang, P.-Y., Li, S.-W., Misra, I., Rabbat, M., Sharma, V., Synnaeve, G., Xu, H., Jégou, H., Mairal, J., Labatut, P., Joulin, A., & Bojanowski, P. (2024). DINOv2: Learning robust visual features without supervision. Transactions on Machine Learning Research. Available online: https://openreview.net/forum?id=a68SUt6zFt (accessed on November 23, 2026).",
 "radford2021clip": "Radford, A., Kim, J. W., Hallacy, C., Ramesh, A., Goh, G., Agarwal, S., Sastry, G., Askell, A., Mishkin, P., Clark, J., Krueger, G., & Sutskever, I. (2021). Learning transferable visual models from natural language supervision. Proceedings of the 38th International Conference on Machine Learning (ICML 2021), PMLR 139, 8748–8763.",
 "lu2022dpmsolverpp": "Lu, C., Zhou, Y., Bao, F., Chen, J., Li, C., & Zhu, J. (2025). DPM-Solver++: Fast solver for guided sampling of diffusion probabilistic models. Machine Intelligence Research, 22(4), 730–751. doi:10.1007/s11633-025-1562-4.",
 "rombach2022ldm": "Rombach, R., Blattmann, A., Lorenz, D., Esser, P., & Ommer, B. (2022). High-resolution image synthesis with latent diffusion models. 2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR), 10674–10685. doi:10.1109/CVPR52688.2022.01042.",
 "podell2023sdxl": "Podell, D., English, Z., Lacey, K., Blattmann, A., Dockhorn, T., Müller, J., Penna, J., & Rombach, R. (2024). SDXL: Improving latent diffusion models for high-resolution image synthesis. The Twelfth International Conference on Learning Representations (ICLR 2024), Vienna, Austria.",
 "wilson1927": "Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. Journal of the American Statistical Association, 22(158), 209–212. doi:10.1080/01621459.1927.10502953.",
 "slalom2019": "Tramèr, F., & Boneh, D. (2019). Slalom: Fast, verifiable and private execution of neural networks in trusted hardware. 7th International Conference on Learning Representations (ICLR 2019), New Orleans, United States.",
 "yuan2022decentral": "Yuan, B., He, Y., Davis, J. Q., Zhang, T., Dao, T., Chen, B., Liang, P., Ré, C., & Zhang, C. (2022). Decentralized training of foundation models in heterogeneous environments. Advances in Neural Information Processing Systems 35 (NeurIPS 2022), 25464–25477.",
 "borzunov2023": "Borzunov, A., Ryabinin, M., Chumachenko, A., Baranchuk, D., Dettmers, T., Belkada, Y., Samygin, P., & Raffel, C. (2023). Distributed inference and fine-tuning of large language models over the internet. Advances in Neural Information Processing Systems 36 (NeurIPS 2023), New Orleans, United States.",
 "zhuang2022": "Zhuang, D., Zhang, X., Song, S., & Hooker, S. (2022). Randomness in neural network training: Characterizing the impact of tooling. Proceedings of Machine Learning and Systems 4 (MLSys 2022), 316–336.",
 "pham2020ase": "Pham, H. V., Qian, S., Wang, J., Lutellier, T., Rosenthal, J., Tan, L., Yu, Y., & Nagappan, N. (2020). Problems and opportunities in training deep learning software systems: An analysis of variance. Proceedings of the 35th IEEE/ACM International Conference on Automated Software Engineering (ASE ’20), 771–783. doi:10.1145/3324884.3416545.",
 "safetynets2017": "Ghodsi, Z., Gu, T., & Garg, S. (2017). SafetyNets: Verifiable execution of deep neural networks on an untrusted cloud. Advances in Neural Information Processing Systems 30 (NIPS 2017), Long Beach, United States.",
 "zkcnn2021": "Liu, T., Xie, X., & Zhang, Y. (2021). zkCNN: Zero knowledge proofs for convolutional neural network predictions and accuracy. Proceedings of the 2021 ACM SIGSAC Conference on Computer and Communications Security (CCS ’21), 2968–2985. doi:10.1145/3460120.3485379.",
 "zkllm2024": "Sun, H., Li, J., & Zhang, H. (2024). zkLLM: Zero knowledge proofs for large language models. Proceedings of the 2024 ACM SIGSAC Conference on Computer and Communications Security (CCS ’24), 4405–4419. doi:10.1145/3658644.3670334.",
 "canetti2011": "Canetti, R., Riva, B., & Rothblum, G. N. (2011). Practical delegation of computation using multiple servers. Proceedings of the 18th ACM Conference on Computer and Communications Security (CCS ’11), 445–454. doi:10.1145/2046707.2046759.",
 "arbitrum2018": "Kalodner, H., Goldfeder, S., Chen, X., Weinberg, S. M., & Felten, E. W. (2018). Arbitrum: Scalable, private smart contracts. 27th USENIX Security Symposium (USENIX Security 18), Baltimore, United States, 1353–1370.",
 "pol2021": "Jia, H., Yaghini, M., Choquette-Choo, C. A., Dullerud, N., Thudi, A., Chandrasekaran, V., & Papernot, N. (2021). Proof-of-learning: Definitions and practice. 2021 IEEE Symposium on Security and Privacy (SP), 1039–1056. doi:10.1109/SP40001.2021.00106.",
 "treering2023": "Wen, Y., Kirchenbauer, J., Geiping, J., & Goldstein, T. (2023). Tree-rings watermarks: Invisible fingerprints for diffusion images. Advances in Neural Information Processing Systems 36 (NeurIPS 2023), New Orleans, United States.",
 "stablesig2023": "Fernandez, P., Couairon, G., Jégou, H., Douze, M., & Furon, T. (2023). The stable signature: Rooting watermarks in latent diffusion models. 2023 IEEE/CVF International Conference on Computer Vision (ICCV), 22409–22420. doi:10.1109/ICCV51070.2023.02053.",
 "anderson2004boinc": "Anderson, D. P. (2004). BOINC: A system for public-resource computing and storage. Fifth IEEE/ACM International Workshop on Grid Computing, Pittsburgh, United States, 4–10. doi:10.1109/GRID.2004.14.",
 "golle2001": "Golle, P., & Mironov, I. (2001). Uncheatable distributed computations. Topics in Cryptology – CT-RSA 2001, Lecture Notes in Computer Science, 2020, 425–440. doi:10.1007/3-540-45353-9_31.",
 "sarmenta2002": "Sarmenta, L. F. G. (2002). Sabotage-tolerance mechanisms for volunteer computing systems. Future Generation Computer Systems, 18(4), 561–572. doi:10.1016/S0167-739X(01)00077-2.",
 "belenkiy2008": "Belenkiy, M., Chase, M., Erway, C. C., Jannotti, J., Küpçü, A., & Lysyanskaya, A. (2008). Incentivizing outsourced computation. Proceedings of the 3rd International Workshop on Economics of Networked Systems (NetEcon ’08), 85–90. doi:10.1145/1403027.1403046.",
 "pham2014contracts": "Pham, V., Khouzani, M. H. R., & Cid, C. (2014). Optimal contracts for outsourced computation. Decision and Game Theory for Security (GameSec 2014), Lecture Notes in Computer Science, 8840, 79–98. doi:10.1007/978-3-319-12601-2_5.",
 "dong2017": "Dong, C., Wang, Y., Aldweesh, A., McCorry, P., & van Moorsel, A. (2017). Betrayal, distrust, and rationality: Smart counter-collusion contracts for verifiable cloud computing. Proceedings of the 2017 ACM SIGSAC Conference on Computer and Communications Security (CCS ’17), 211–227. doi:10.1145/3133956.3134032.",
 "luu2015": "Luu, L., Teutsch, J., Kulkarni, R., & Saxena, P. (2015). Demystifying incentives in the consensus computer. Proceedings of the 22nd ACM SIGSAC Conference on Computer and Communications Security (CCS ’15), 706–719. doi:10.1145/2810103.2813659.",
 "kumaresan2014": "Kumaresan, R., & Bentov, I. (2014). How to use bitcoin to incentivize correct computations. Proceedings of the 2014 ACM SIGSAC Conference on Computer and Communications Security (CCS ’14), 30–41. doi:10.1145/2660267.2660380.",
 "fairswap2018": "Dziembowski, S., Eckey, L., & Faust, S. (2018). FairSwap: How to fairly exchange digital goods. Proceedings of the 2018 ACM SIGSAC Conference on Computer and Communications Security (CCS ’18), 967–984. doi:10.1145/3243734.3243857.",
}
order = []  # citation keys in order of first appearance


def cite_numbers(keys):
    nums = []
    for k in keys:
        k = k.strip()
        if k not in REFS:
            raise KeyError(f"no reference entry for {k}")
        if k not in order:
            order.append(k)
        nums.append(order.index(k) + 1)
    nums = sorted(set(nums))
    parts, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        parts.append(str(nums[i]) if i == j else (f"{nums[i]}, {nums[j]}" if j == i + 1 else f"{nums[i]}–{nums[j]}"))
        i = j + 1
    return "[" + ", ".join(parts) + "]"


# ----------------------------------------------------------------------------------------------
# Rich text -> runs
# ----------------------------------------------------------------------------------------------
TOKEN = re.compile(r"\{(b|i|bi|sub|sup|R|T|c)\|([^{}]*)\}")


def parse(text):
    """yield (string, fmt-set)"""
    pos = 0
    for m in TOKEN.finditer(text):
        if m.start() > pos:
            yield text[pos:m.start()], set()
        kind, val = m.group(1), m.group(2)
        if kind == "c":
            yield cite_numbers(val.split(",")), set()
        elif kind == "R":
            yield "[" + val + "]", {"red", "b"}
        elif kind == "T":
            yield "[TODO: " + val + "]", {"blue"}
        elif kind == "bi":
            yield val, {"b", "i"}
        else:
            yield val, {kind}
        pos = m.end()
    if pos < len(text):
        yield text[pos:], set()


def make_run(base_rpr, s, fmt):
    r = etree.SubElement(etree.Element(qn("w:dummy")), qn("w:r"))
    rpr = copy.deepcopy(base_rpr) if base_rpr is not None else etree.Element(qn("w:rPr"))
    def setflag(tag, val=None):
        for old in rpr.findall(qn(tag)):
            rpr.remove(old)
        el = etree.SubElement(rpr, qn(tag))
        if val is not None:
            el.set(qn("w:val"), val)
    if "b" in fmt:
        setflag("w:b")
    if "i" in fmt:
        setflag("w:i")
    if "sub" in fmt:
        setflag("w:vertAlign", "subscript")
    if "sup" in fmt:
        setflag("w:vertAlign", "superscript")
    if "red" in fmt:
        setflag("w:color", RED)
    if "blue" in fmt:
        setflag("w:color", BLUE)
    # schema order inside rPr matters for strict validators; sort by a canonical order
    ORDER = ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "noProof", "color",
             "spacing", "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect", "shd", "vertAlign", "lang"]
    kids = list(rpr)
    kids.sort(key=lambda e: ORDER.index(etree.QName(e).localname) if etree.QName(e).localname in ORDER else 99)
    for k in kids:
        rpr.remove(k)
    for k in kids:
        rpr.append(k)
    for rf in rpr.findall(qn("w:rFonts")):
        rf.attrib.pop(qn("w:hint"), None)
    for lg in rpr.findall(qn("w:lang")):
        lg.attrib.pop(qn("w:eastAsia"), None)
    r.append(rpr)
    t = etree.SubElement(r, qn("w:t"))
    t.text = s
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return r


def fill_para(p_el, text, base_rpr=None):
    """Remove all content but pPr from paragraph element and add runs from markup text."""
    for child in list(p_el):
        if child.tag != qn("w:pPr"):
            p_el.remove(child)
    for s, fmt in parse(text):
        if s:
            p_el.append(make_run(base_rpr, s, fmt))
    return p_el


def first_rpr(p_el):
    r = p_el.find(qn("w:r"))
    if r is None:
        return None
    rpr = r.find(qn("w:rPr"))
    return copy.deepcopy(rpr) if rpr is not None else None


# ----------------------------------------------------------------------------------------------
# OMML builder
# ----------------------------------------------------------------------------------------------
def mr(text, plain=False):
    sty = '<m:rPr><m:sty m:val="p"/></m:rPr>' if plain else ""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<m:r>{sty}<m:t xml:space="preserve">{text}</m:t></m:r>'


def R(*parts):
    """concatenate fragments; plain strings become italic math runs, ('p', s) plain runs"""
    out = []
    for p in parts:
        if isinstance(p, tuple):
            out.append(mr(p[1], plain=True))
        elif p.startswith("<m:"):
            out.append(p)
        else:
            out.append(mr(p))
    return "".join(out)


def sub(base, s):
    return f"<m:sSub><m:e>{R(base)}</m:e><m:sub>{R(s)}</m:sub></m:sSub>"


def sup(base, s):
    return f"<m:sSup><m:e>{R(base)}</m:e><m:sup>{R(s)}</m:sup></m:sSup>"


def frac(n, d, nobar=False):
    pr = '<m:fPr><m:type m:val="noBar"/></m:fPr>' if nobar else ""
    return f"<m:f>{pr}<m:num>{R(n)}</m:num><m:den>{R(d)}</m:den></m:f>"


def delim(content, beg="(", end=")"):
    return f'<m:d><m:dPr><m:begChr m:val="{beg}"/><m:endChr m:val="{end}"/></m:dPr><m:e>{R(content)}</m:e></m:d>'


def binom(a, b):
    return delim(frac(a, b, nobar=True))


def nsum(lo, hi, body):
    return (f'<m:nary><m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="undOvr"/></m:naryPr>'
            f"<m:sub>{R(lo)}</m:sub><m:sup>{R(hi)}</m:sup><m:e>{R(body)}</m:e></m:nary>")


def maxover(var, body):
    return (f"<m:func><m:fName><m:limLow><m:e>{mr('max', True)}</m:e><m:lim>{R(var)}</m:lim></m:limLow></m:fName>"
            f"<m:e>{R(body)}</m:e></m:func>")


def omath(*parts):
    xml = f'<m:oMath xmlns:m="{M}" xmlns:w="{W}">{R(*parts)}</m:oMath>'
    return etree.fromstring(xml)


# ----------------------------------------------------------------------------------------------
# Document assembly
# ----------------------------------------------------------------------------------------------
def main(template, out):
    doc = docx.Document(template)
    body = doc.element.body
    P = doc.paragraphs
    T = doc.tables

    proto = {
        "h1": copy.deepcopy(P[10]._p), "body": copy.deepcopy(P[11]._p), "h2": copy.deepcopy(P[12]._p),
        "bullet": copy.deepcopy(P[15]._p), "caption": copy.deepcopy(P[21]._p),
        "figpara": copy.deepcopy(P[22]._p), "decl": copy.deepcopy(P[25]._p), "ref": copy.deepcopy(P[57]._p),
        "eqtbl": copy.deepcopy(T[2]._tbl),
    }
    rpr = {k: first_rpr(v) for k, v in proto.items() if k != "eqtbl"}
    h2_ppr = proto["h2"].find(qn("w:pPr"))
    for old in h2_ppr.findall(qn("w:numPr")):
        h2_ppr.remove(old)
    num = etree.SubElement(h2_ppr, qn("w:numPr"))
    etree.SubElement(num, qn("w:ilvl")).set(qn("w:val"), "0")
    etree.SubElement(num, qn("w:numId")).set(qn("w:val"), "0")
    # numPr must follow pStyle/keepNext etc. in schema order: move it right after pStyle
    h2_ppr.remove(num)
    ps = h2_ppr.find(qn("w:pStyle"))
    (ps.addnext(num) if ps is not None else h2_ppr.insert(0, num))

    # ---- front matter (edit in place) ----
    fill_para(P[1]._p, TITLE, first_rpr(P[1]._p))
    a_base, a_sup = first_rpr(P[3]._p), None
    for r in P[3].runs:
        if r.font.superscript:
            a_sup = copy.deepcopy(r._r.find(qn("w:rPr")))
            break
    ap = P[3]._p
    footnote_ref = None
    for r in ap.findall(qn("w:r")):
        if r.find(qn("w:footnoteReference")) is not None:
            footnote_ref = copy.deepcopy(r)
    fill_para(ap, "", a_base)
    for s, fmt, is_sup in AUTHORS:
        if s == "<FN>":
            if footnote_ref is not None:
                ap.append(footnote_ref)
            continue
        ap.append(make_run(a_sup if is_sup else a_base, s, fmt))
    affil3_p = copy.deepcopy(P[5]._p)  # template has two affiliation lines; clone the second
    P[5]._p.addnext(affil3_p)
    for p_el, text in ((P[4]._p, AFFIL1), (P[5]._p, AFFIL2), (affil3_p, AFFIL3)):
        runs = p_el.findall(qn("w:r"))
        sup_rpr = copy.deepcopy(runs[0].find(qn("w:rPr"))) if runs else None
        base = None
        for r in runs:
            rp = r.find(qn("w:rPr"))
            if rp is None or rp.find(qn("w:vertAlign")) is None:
                base = copy.deepcopy(rp) if rp is not None else None
                break
        num, rest = text
        fill_para(p_el, "", base)
        p_el.append(make_run(sup_rpr, num, set()))
        for s, fmt in parse(rest):
            p_el.append(make_run(base, s, fmt))

    cell0, cell1 = T[0].rows[0].cells
    abs_p = cell0.paragraphs[1]._p
    fill_para(abs_p, ABSTRACT, first_rpr(abs_p))
    kw_p = cell1.paragraphs[0]._p
    kw_runs = kw_p.findall(qn("w:r"))
    kw_bold, kw_plain = copy.deepcopy(kw_runs[0].find(qn("w:rPr"))), copy.deepcopy(kw_runs[1].find(qn("w:rPr")))
    fill_para(kw_p, "", kw_plain)
    kw_p.append(make_run(kw_bold, "Keywords: ", set()))
    kw_p.append(make_run(kw_plain, KEYWORDS, set()))

    # ---- remove the template's example body ----
    sect = body.find(qn("w:sectPr"))
    start = P[10]._p
    started = False
    for el in list(body):
        if el is start:
            started = True
        if started and el is not sect:
            body.remove(el)

    def add(el):
        sect.addprevious(el)
        return el

    counters = {"table": 0, "figure": 0, "eq": 0}

    def H1(t): add(fill_para(copy.deepcopy(proto["h1"]), t, rpr["h1"]))
    def H2(t): add(fill_para(copy.deepcopy(proto["h2"]), t, rpr["h2"]))
    def Para(t, kind="body"): add(fill_para(copy.deepcopy(proto[kind]), t, rpr[kind]))
    def Bullets(items):
        for t in items:
            add(fill_para(copy.deepcopy(proto["bullet"]), t, rpr["bullet"]))

    def Caption(kind, text):
        counters[kind] += 1
        label = "Table" if kind == "table" else "Figure"
        add(fill_para(copy.deepcopy(proto["caption"]), f"{label} {counters[kind]}. {text}", rpr["caption"]))
        return counters[kind]

    def Figure(pid, desc, caption, image=None):
        fp = copy.deepcopy(proto["figpara"])
        if image:
            # a drawn figure from paper/figures/, centred at the text width (168 mm)
            add(fill_para(fp, "", rpr["figpara"]))
            para = docx.text.paragraph.Paragraph(fp, doc._body)
            para.alignment = 1
            para.paragraph_format.first_line_indent = Mm(0)
            para.paragraph_format.left_indent = Mm(0)
            para.paragraph_format.keep_with_next = True
            fig_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "figures")
            para.add_run().add_picture(os.path.join(fig_dir, image), width=Mm(165))
        else:
            add(fill_para(fp, "{R|FIGURE " + pid + ": " + desc + "}", rpr["figpara"]))
        return Caption("figure", caption)

    def Table(caption, header, rows, widths_mm):
        Caption("table", caption)
        tbl = doc.add_table(rows=1 + len(rows), cols=len(header))  # inserted before sectPr
        tbl.style = doc.styles["Table Grid"]
        tbl.alignment = 1
        for ri, row in enumerate([header] + rows):
            for ci, txt in enumerate(row):
                cell = tbl.rows[ri].cells[ci]
                cell.width = Mm(widths_mm[ci])
                p = cell.paragraphs[0]
                p.style = doc.styles["table-text"]
                fill_para(p._p, ("{b|" + txt + "}") if ri == 0 and "{" not in txt else txt)
        # spacer paragraph after table
        add(fill_para(copy.deepcopy(proto["body"]), "", rpr["body"]))

    def Eq(math_el):
        counters["eq"] += 1
        t = copy.deepcopy(proto["eqtbl"])
        om = t.find(".//" + qn("m:oMath"))
        om.getparent().replace(om, math_el)
        cells = t.findall(".//" + qn("w:tc"))
        numcell_p = cells[1].find(qn("w:p"))
        fill_para(numcell_p, f"({counters['eq']})", first_rpr(numcell_p))
        add(t)
        return counters["eq"]

    build_body(H1, H2, Para, Bullets, Figure, Table, Eq)

    # ---- references ----
    H1("7- References")
    for n, key in enumerate(order, 1):
        add(fill_para(copy.deepcopy(proto["ref"]), f"[{n}] " + REFS[key], rpr["ref"]))

    doc.core_properties.title = "Calibrated Trajectory Verification for Escrow-Settled Diffusion Inference"
    doc.core_properties.author = "Anjas Risky Maradita; Dito Eka Cahya; Ekki Rinaldi; Pujianto Yugopuspito"
    doc.save(out)

    # footnote contact e-mail (template placeholder)
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(out) as z:
        z.extractall(tmp)
    fpath = os.path.join(tmp, "word", "footnotes.xml")
    with open(fpath, encoding="utf8") as f:
        xml = f.read()
    # the template splits the e-mail into two runs: "a" + "uthor@institute.xxx"
    i_contact = xml.find("CONTACT")
    i_a = xml.find("<w:t>a</w:t>", i_contact)
    if i_contact >= 0 and i_a >= 0:
        xml = xml[:i_a] + "<w:t></w:t>" + xml[i_a + len("<w:t>a</w:t>"):]
    xml = xml.replace("<w:t>uthor@institute.xxx</w:t>", "<w:t>TODO-corresponding-author-email</w:t>")
    assert "institute.xxx" not in xml, "footnote e-mail placeholder not replaced"
    with open(fpath, "w", encoding="utf8") as f:
        f.write(xml)
    os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(tmp):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, tmp).replace(os.sep, "/"))
    shutil.rmtree(tmp)
    print("references:", len(order), "| tables:", counters["table"], "| figures:", counters["figure"], "| equations:", counters["eq"])


# ----------------------------------------------------------------------------------------------
# CONTENT
# ----------------------------------------------------------------------------------------------
TITLE = "Calibrated Trajectory Verification for Escrow-Settled Diffusion Inference on Heterogeneous GPUs"
AUTHORS = [("Anjas Risky Maradita", set(), False), (" 1", set(), True), ("<FN>", set(), True),
           (", ", set(), False), ("Dito Eka Cahya", set(), False), (" 2", set(), True),
           (", ", set(), False), ("Ekki Rinaldi", set(), False), (" 3", set(), True),
           (", ", set(), False), ("Pujianto Yugopuspito", set(), False), (" 1", set(), True)]
AFFIL1 = ("1 ", "Faculty of Artificial Intelligence and Data Science, Universitas Pelita Harapan, Jakarta, Indonesia.")
AFFIL2 = ("2 ", "Research Center for AI and Cybersecurity, National Research and Innovation Agency of Indonesia, Jakarta, Indonesia.")
AFFIL3 = ("3 ", "Founder, Vektor Labs, Jakarta, Indonesia.")
KEYWORDS = "Decentralized GPU Marketplace; Verifiable Inference; Diffusion Models; Probabilistic Verification; Smart-Contract Escrow; DePIN."

ABSTRACT = (
 "Decentralized GPU marketplaces pay untrusted owners of consumer GPUs to run generative AI jobs. For diffusion "
 "models, a provider can lower its cost without returning an obviously wrong image, by running fewer denoising steps, "
 "a quantized or distilled model, or by fabricating intermediate sampler states. Re-executing the job on another GPU "
 "rarely gives a bit-identical result, so every acceptance rule must tolerate honest variation, and that tolerance is "
 "where cheating can hide. {b|Objectives:} this study determines what evidence a marketplace must demand to detect "
 "cost-saving cheating on diffusion jobs, and at what cost. {b|Methods:} honest variation of pinned ComfyUI SD1.5 and "
 "SDXL workflows is measured across five nested heterogeneity levels on DGX Spark systems and rented GeForce RTX 3090, RTX 4090 and RTX 5090 cards. Two validation rules deployed on a public decentralized network are reproduced and attacked with "
 "eight candidate cost-saving attacks and four trajectory forgeries. A two-tier trajectory check is proposed. It verifies solver "
 "consistency on every step on the CPU and model consistency at k random steps under per-step calibrated tolerances, "
 "binds the initial noise to the seed, and settles through a Solana escrow with a provider bond. {b|Findings:} "
 + RW.abstract_findings() + ". "
 "{b|Novelty:} an analytical model shows that any output-only rule has a detection ceiling that sampling cannot raise, "
 "and that under step spot checks a rational provider cheats either fully or not at all. This yields a closed-form "
 "deterrence condition and a cost-optimal sampling policy. {R|NEEDS WORK: the forgery results and the cost saving "
 "β_A are being re-measured; update the Findings sentence afterwards}"
)


def build_body(H1, H2, Para, Bullets, Figure, Table, Eq):
    # ================================================================== 1 INTRODUCTION
    H1("1- Introduction")
    Para("Generative artificial intelligence (AI) has turned graphics processing units (GPUs) into one of the most "
         "contested computing resources. Large cloud providers own most data-centre accelerators, while a large and "
         "growing pool of consumer GPUs in homes, studios and laboratories sits idle for much of the day. Decentralized "
         "physical infrastructure networks (DePIN) aim to bridge the two by pooling independently owned hardware through "
         "blockchain coordination and token payments {c|ballandies2023depin,lin2024depin}. Research systems have shown "
         "that collaborative inference {c|borzunov2023} and training {c|yuan2022decentral} over heterogeneous GPUs "
         "connected through the internet are technically viable, and commercial compute markets such as Render, Akash "
         "and io.net, together with networks dedicated to image generation, already sell GPU time from such providers "
         "{c|render2023,akash2026,ionet2026,nicheimage_repo,wombo_repo}.")
    Para("These markets move computation across a trust boundary. The buyer, called the requester here, cannot observe "
         "what happens on the provider’s machine. A blockchain can record that a payment was escrowed, that a result "
         "digest was committed at a certain time and that a verdict was reached, but it cannot show that the provider ran "
         "the requested model, for the requested number of steps, at the requested numerical precision. The underlying "
         "problem is old: volunteer computing projects found two decades ago that some participants return results they "
         "did not compute {c|golle2001,sarmenta2002}. What is new is the form it takes for generative AI on heterogeneous "
         "GPUs.")
    Para("Diffusion models are a natural place to study this problem. Text-to-image generation with latent diffusion "
         "models {c|rombach2022ldm,podell2023sdxl} is one of the most common consumer GPU workloads, and open-source "
         "workflow engines such as ComfyUI {c|comfyui} make it easy to package as a job. A diffusion job is iterative: a "
         "sampler refines a latent over T steps, and each step calls a large denoising network, so the cost of a job grows "
         "with the number of steps, the size of the network and its numerical precision. The cheapest ways to cheat follow "
         "directly from this structure, and none of them produces garbage. A provider that runs 20 instead of 30 steps "
         "or substitutes a distilled “turbo” model returns an image that looks plausible and is often semantically close "
         "to the honest one, while saving a large share of the job’s GPU time. Storing the network in 8-bit floating "
         "point (fp8), a single command-line flag in ComfyUI, reduces memory and, where fast low-precision kernels exist, "
         "time.")
    Para("Detecting such cost-saving substitution from outputs alone is already known to be very hard for large "
         "language models (LLMs): classifiers trained to recognise quantized model outputs perform at chance level, and "
         "statistical tests lose power when only part of the traffic is substituted {c|cai2025substitution,gao2025met}. "
         "For diffusion models it has not been measured. The obvious defence, re-executing a random sample of jobs on an "
         "independent node, faces two obstacles. First, honest re-execution on different hardware is not bit-exact, "
         "because kernels, reduction order, attention implementations and precision differ across GPUs and software stacks "
         "{c|diffusers_repro,zhuang2022,yuan2025nondeterminism}. Every practical acceptance rule therefore needs a "
         "tolerance, and the tolerance determines both how often honest providers are falsely rejected and how much room "
         "is left for cheaters. Second, full re-execution doubles the cost of each audited job.")
    Para("Existing remedies sit at two extremes. Cryptographic proofs and trusted hardware give strong guarantees but "
         "are too slow, or require hardware that consumer providers do not have {c|chen2024zkml,slalom2019}. Protocols "
         "that compare intermediate values at the level of individual operators need instrumented runtimes, and the most "
         "recent of them explicitly leaves undeclared quantization and early exit out of scope {c|yao2026tao}. At the "
         "other extreme, the validators deployed today in decentralized image networks compare final images or a few "
         "intermediate latents against thresholds that were never calibrated or tested against attacks "
         "{c|nicheimage_repo,wombo_repo}.")
    Para("This paper exploits a structure that diffusion sampling exposes for free. The sequence of latents and denoised "
         "predictions produced by the sampler, its trajectory, can be recorded through a hook in the sampler without "
         "touching the model’s operators. The provider commits to the full trajectory before it knows whether the job will "
         "be checked. A verifier then checks the arithmetic of every sampler step on a CPU at negligible cost, re-runs the "
         "denoising network at only k randomly chosen steps, and accepts each step under a tolerance calibrated on "
         "measured cross-GPU variation. A smart-contract escrow with a provider bond turns detection into a financial "
         "penalty, and an analytical model shows when that penalty deters a rational provider. The same structure exists, "
         "in principle, in other iterative generators such as flow-matching and video diffusion models, which are left to "
         "future work.")
    H2("1-1- Research Questions")
    Para("The study answers three research questions (RQs), designed so that each yields a useful answer whatever the "
         "data show:")
    Bullets(["{b|RQ1 (Characterize).} How much do honest ComfyUI diffusion outputs vary across GPUs and software "
             "configurations, at the level of the final image, the per-step latent and the single sampler step, and which "
             "factors drive the variation?",
             "{b|RQ2 (Separate).} At a false-rejection rate of at most 1%, which cost-saving attacks and trajectory "
             "forgeries can be detected at each evidence level, and how do deployed validation rules fare against them?",
             "{b|RQ3 (Price).} What verifier cost, on-chain cost and latency reach a stated detection and deterrence target "
             "under sampled verification with escrow, and how does step-level spot checking change the cost-optimal "
             "sampling policy?"])
    H2("1-2- Contributions")
    Bullets(["A measurement of honest variation for SD1.5 and SDXL workflows across five nested heterogeneity levels, "
             "from repeated runs on one GPU to different GPU generations, including an exact-reproducibility test of the "
             "initial noise across x86 and ARM processors.",
             "An attack study of faithful reproductions of two deployed validation rules against eight candidate cost-saving attacks "
             "and four trajectory forgeries, with calibrated error rates.",
             "A hardened two-tier trajectory check that needs only a sampler hook, not operator-level access or trusted "
             "hardware, integrated with a Solana escrow that holds a provider bond.",
             "An analytical model: an output-only detection ceiling, the detection probability of step spot checks under "
             "partial cheating, and a proof that a rational provider’s best response is all-or-nothing, which gives a "
             "closed-form deterrence condition and a cost-optimal sampling policy.",
             "An open artifact with code, data and frozen thresholds (https://github.com/ditoec/decentralized-research; {R|R0.2: Zenodo DOI})."])
    Para("In short: " + RW.narr_r29() + " Section 2 reviews related work, Section 3 describes "
         "the materials and methods, Section 4 reports and discusses the results, and Section 5 concludes.")

    # ================================================================== 2 RELATED WORK
    H1("2- Related Work")
    Para("Work relevant to this paper spans decentralized computing, verifiable computation, auditing of AI services, "
         "incentive design and numerical reproducibility. The review is organized by the evidence a verifier receives, "
         "from the strongest (a proof) to the weakest (an output), followed by the incentive and reproducibility work on "
         "which any sampling scheme depends. Table 1 summarizes the closest approaches.")
    H2("2-1- Decentralized GPU Computing")
    Para("DePIN systems coordinate independently owned hardware through blockchain incentives; Ballandies et al. "
         "{c|ballandies2023depin} propose a taxonomy of such networks, and Lin et al. {c|lin2024depin} survey their "
         "challenges and opportunities. For machine learning, Petals {c|borzunov2023} runs inference and fine-tuning of "
         "large language models across unreliable consumer devices connected through the internet, and Yuan et al. "
         "{c|yuan2022decentral} schedule the training of foundation models over heterogeneous, geographically distributed "
         "GPUs. Commercial markets sell GPU time from independent providers {c|render2023,akash2026,ionet2026}. This line "
         "of work establishes that decentralized GPU computing is feasible and economically attractive. Its focus is "
         "performance, scheduling and fault tolerance; checking that a provider actually performed the computation it "
         "was paid for is left to other mechanisms, which the following subsections review.")
    H2("2-2- Cryptographic and Hardware-Based Verification")
    Para("Verifiable computation lets a client check an outsourced computation with a short proof "
         "{c|gennaro2010vc}. Interactive proofs specialized to neural networks reduce the cost at the price of "
         "restricted arithmetic {c|safetynets2017}, and zero-knowledge proof systems have since proved convolutional "
         "networks {c|zkcnn2021}, large language models {c|zkllm2024} and a small latent diffusion model {c|chen2024zkml}. "
         "These proofs give the strongest guarantee available, but their proving cost, about an hour per image for the "
         "diffusion model, is far above the price of the computation being sold in a marketplace.")
    Para("Trusted execution environments take a hardware route. Slalom {c|slalom2019} runs a network inside a secure "
         "enclave, outsources its linear layers to an untrusted GPU and checks those layers probabilistically. The "
         "approach is efficient, but it requires trusted hardware on every provider, which is uncommon on consumer GPUs. "
         "Both families give guarantees that do not depend on numerical tolerances, and both are a poor fit for "
         "anonymous consumer hardware today.")
    H2("2-3- Re-Execution with Disputes and Tolerances")
    Para("A cheaper family re-executes only what is disputed. Refereed delegation lets a client detect cheating "
         "whenever at least one of several servers is honest {c|canetti2011}, and optimistic blockchain protocols resolve "
         "disputes by bisecting a computation down to a single step that an on-chain referee can check {c|arbitrum2018}. "
         "Verde {c|arun2025verde} adapts refereed delegation to machine learning; to make honest results agree, it "
         "replaces the operator library with bitwise-reproducible operators. EigenAI {c|alves2026eigenai} pursues the "
         "same goal by enforcing deterministic inference, so that verification reduces to a byte comparison. Both buy "
         "exactness by controlling the software stack.")
    Para("TAO {c|yao2026tao} takes the opposite route and accepts that honest results differ. It commits to the "
         "weights, the computation graph and per-operator error thresholds calibrated on four GPU models, narrows "
         "disputes to one operator, and settles with bonds and randomized audits on an Ethereum test network, with "
         "0.3% overhead on the undisputed path. It is the closest system to this paper. Its evidence, however, is "
         "operator-level and requires an instrumented runtime; diffusion appears only in its cost evaluation, "
         "per-step verification of the denoising loop is left to future work, and undeclared quantization and early "
         "exit are explicitly out of scope.")
    Para("Proof-of-learning {c|pol2021} is the closest precedent for trajectory checking. A trainer commits checkpoints "
         "of its training trajectory, and a verifier re-executes selected update steps and accepts reproduction errors "
         "below a threshold that absorbs hardware noise. The idea of committing to an iterative computation and "
         "re-checking a few steps under a tolerance is shared with this paper; the setting is not. Proof-of-learning "
         "targets training, where each step is a gradient update, and does not consider cost-saving substitution during "
         "inference.")
    H2("2-4- Activation-Based Checks for Language Models")
    Para("For LLM inference, several schemes commit to compact fingerprints of internal activations. TOPLOC "
         "{c|ong2025toploc} hashes the top-k activation values with a locality-sensitive encoding, so that a verifier "
         "who recomputes the activations can check them at a small fraction of the original cost. VeriLLM "
         "{c|wang2025verillm} combines sampled checks of hidden states with lightweight on-chain settlement and reports a "
         "verification cost of about 1% of inference. These schemes show that intermediate state is far more "
         "informative than the final output. They require access to the model’s internals and target autoregressive "
         "language models; for diffusion, the sampler trajectory used in this paper plays the role of the activation "
         "fingerprint and is available without modifying the model.")
    H2("2-5- Black-Box Auditing and Output Attribution")
    Para("When only outputs are visible, auditing becomes a statistical test. Model equality testing {c|gao2025met} "
         "frames the question as a two-sample test between an API and reference weights, and found that 11 of 31 "
         "commercial Llama endpoints deviated from the reference. Cai et al. {c|cai2025substitution} show the limits of "
         "this approach for cost-saving substitution: classifiers distinguish fp8 or int8 models from full precision only "
         "at chance level, statistical tests lose power when only part of the traffic is substituted, and honest "
         "deployments of the same model already differ. Cross-GPU variation creates the same difficulty for diffusion "
         "models. For images, Kim et al. {c|kim2024reproducibility} measured perceptual-hash agreement of Stable Diffusion "
         "outputs on 22 GPUs of five models and analysed majority voting among verifiers, without modelling an adversary.")
    Para("Watermarking offers a different kind of output evidence. Tree-Ring watermarks {c|treering2023} embed a "
         "pattern in the initial noise that can be recovered from the image, and Stable Signature {c|stablesig2023} "
         "fine-tunes the latent decoder so that every image it produces carries a mark. Watermarks attribute an image "
         "to a model, but they do not show how the image was computed: a provider that runs the advertised model with "
         "fewer steps would still produce a correctly watermarked image.")
    H2("2-6- Validators in Deployed Decentralized Image Networks")
    Para("Two image-generation subnets of a public decentralized AI network show how verification is done in practice. "
         "The first regenerates each audited image on the validator and compares CLIP {c|radford2021clip} image "
         "embeddings of the two images, giving full reward above a cosine similarity of 0.9; an alternative path "
         "accepts perceptual hashes within a Hamming distance of 6 {c|nicheimage_repo}. The second asks miners to "
         "return every per-step latent together with a SHA-256 commitment. With probability 0.35 its validator samples "
         "three steps, re-runs one denoising step from each reported latent, and rejects the response if the minimum "
         "cosine similarity to the reported next latent falls below 0.70 {c|wombo_repo}.")
    Para("The second rule is, to our knowledge, the earliest deployment of per-step spot checking, and this paper "
         "does not claim the mechanism as new. Neither rule, however, has a published calibration against honest "
         "cross-GPU variation or an evaluation against attacks. Whether a cosine threshold of 0.70 on flattened latents "
         "separates honest work from cheap forgeries is an open empirical question that this paper tests.")
    H2("2-7- Spot Checking, Incentives and the Verifier’s Dilemma")
    Para("Sampling-based verification has a long history outside blockchains. Volunteer computing projects replicate "
         "tasks across hosts and compare results {c|anderson2004boinc}; Golle and Mironov {c|golle2001} plant tasks with "
         "known answers, called ringers, to catch participants who skip their share; and Sarmenta {c|sarmenta2002} shows "
         "that spot-checking combined with per-worker credibility scores bounds the error rate with less redundancy than "
         "voting. In outsourced computing, Belenkiy et al. {c|belenkiy2008} and Pham et al. {c|pham2014contracts} design "
         "contracts that audit a random fraction of jobs and fine cheaters, choosing the audit rate and penalty so that "
         "honesty is the provider’s best response. Dong et al. {c|dong2017} add counter-collusion contracts that deter "
         "redundant cloud providers from agreeing on a wrong answer, and Proof of Sampling {c|zhang2024posp} applies an "
         "equilibrium argument to sampled verification of decentralized AI inference.")
    Para("Two further results shape the design of any such scheme. The verifier’s dilemma {c|luu2015} shows that "
         "rational verifiers skip costly checks unless they are rewarded for performing them. Blockchain contracts can "
         "enforce payment for correct computation {c|kumaresan2014} and fair exchange of digital goods "
         "{c|fairswap2018,asgaonkar2018escrow}, and markets for edge and federated-learning resources "
         "{c|du2023edgemarket,fan2021hybrid,wang2024stackelberg,yang2019survey} price and allocate computation. Almost all "
         "of this work treats correctness as binary and assumes that an honest re-execution reproduces the result "
         "exactly. Neither assumption holds for diffusion inference on heterogeneous GPUs, and Proposition 3 of this "
         "paper shows how the detection structure of step spot checks changes the incentive analysis.")
    H2("2-8- Numerical Nondeterminism of GPU Inference")
    Para("Floating-point addition is not associative, and GPUs reorder it freely. As a result, the same model with the "
         "same inputs can produce different outputs across GPU models, batch sizes, library versions and attention "
         "implementations. In training, nondeterministic GPU kernels alone produce run-to-run variance in the resulting "
         "models {c|zhuang2022}, and such variance is large and often unreported {c|pham2020ase}. In LLM inference, "
         "greedy outputs can diverge when the GPU count, the batch size or the hardware changes, especially at 16-bit "
         "precision {c|yuan2025nondeterminism}, and a lack of batch invariance in serving kernels is a major cause "
         "{c|he2025nondeterminism}. Recent work targets reproducing GPU-level nondeterminism itself {c|hawkeye2026}.")
    Para("For diffusion models, library documentation warns that full reproducibility across hardware is not "
         "guaranteed and recommends generating the initial noise on the CPU {c|diffusers_repro}. Deterministic samplers "
         "such as Euler and DPM-Solver++ {c|lu2022dpmsolverpp} add no fresh noise after the first step, so any "
         "difference between two honest runs comes from numerics alone. Apart from the perceptual-hash study of Kim et "
         "al. {c|kim2024reproducibility}, how large these differences are at the level of individual sampler steps, and "
         "which hardware and software factors drive them, has not been measured.")
    H2("2-9- Summary and Research Gap")
    Table("Positioning against the closest work",
          ["Work", "Evidence used", "No operator-level access", "Diffusion", "Cost-saving attacks evaluated", "Calibrated false-rejection rate"],
          [["Volunteer-computing spot checks {c|sarmenta2002}", "Re-execution of sampled tasks", "Yes", "No", "No", "No"],
           ["zkCNN, zkLLM, ZKML {c|zkcnn2021,zkllm2024,chen2024zkml}", "Zero-knowledge proof", "No", "Partial", "n/a", "n/a"],
           ["TOPLOC, VeriLLM {c|ong2025toploc,wang2025verillm}", "Activations", "No", "No", "Partial", "Yes"],
           ["Proof-of-learning {c|pol2021}", "Training-trajectory checkpoints", "Yes", "No", "Partial", "Yes"],
           ["Verde {c|arun2025verde}", "Reproducible operators", "No", "No", "No", "n/a"],
           ["TAO {c|yao2026tao}", "Per-operator tolerance", "No", "Cost only", "Excluded", "Yes"],
           ["Kim et al. {c|kim2024reproducibility}", "Output perceptual hash", "Yes", "Yes", "No", "No"],
           ["Cai et al. {c|cai2025substitution}", "Output text", "Yes", "No", "Yes", "n/a"],
           ["Deployed SN23 rule {c|nicheimage_repo}", "Output embedding", "Yes", "Yes", "No", "No"],
           ["Deployed SN30 rule {c|wombo_repo}", "Per-step latents", "Yes", "Yes", "No", "No"],
           ["{b|This work}", "{b|Trajectory, two-tier}", "{b|Yes}", "{b|Yes}", "{b|Yes}", "{b|Yes}"]],
          [38, 32, 24, 20, 28, 26])
    Para("Table 1 shows that no existing approach combines the four properties a diffusion marketplace needs: evidence "
         "that can be collected without instrumenting the model’s operators, coverage of diffusion workloads, evaluation "
         "against cost-saving attacks, and a false-rejection rate calibrated on honest hardware variation. The gap has "
         "three parts, each addressed by one research question:")
    Bullets(["{b|Measurement (RQ1).} Honest variation of diffusion outputs across GPUs has been measured only at the "
             "level of final-image perceptual hashes, not per sampler step and not by heterogeneity factor.",
             "{b|Separation (RQ2).} Whether cost-saving attacks can be told apart from honest variation, at which "
             "evidence level, and whether the deployed validators do so, has not been tested.",
             "{b|Price (RQ3).} Classical audit contracts assume exact re-execution; the cost and deterrence of "
             "tolerance-based step spot checks under escrow settlement have not been analysed or measured."])

    # ================================================================== 3 MATERIALS AND METHODS
    H1("3- Materials and Methods")
    Para("Figure 1 shows the research methodology. The protocol and the analytical model (Sections 3-1 to 3-3) define "
         "what is measured, and the experiments (Section 3-4) measure honest variation, attack separability and cost.")
    Figure("F1", "Flowchart of the research methodology: system and threat model → protocol and evidence levels → "
           "analytical model → hardware and workload setup → RQ1 honest-variation study → calibration and threshold "
           "freezing → RQ2 attack study → RQ3 cost and deterrence → conclusions.",
           "Flowchart of the research methodology", image="fig1_methodology.png")
    H2("3-1- System and Threat Model")
    Para("A {i|requester} submits a diffusion job and escrows a payment P. A {i|provider} owns a GPU and runs the job. A "
         "{i|verifier} is an independent node that re-executes parts of sampled jobs. An {i|orchestrator} matches jobs to "
         "providers and relays state transitions. An {i|escrow program} on Solana {c|yakovenko2018solana} holds P, an "
         "optional provider bond B and a verifier fee, and releases or refunds them according to the recorded job state "
         "and a timeout. Each job specifies a pinned ComfyUI workflow: checkpoint hashes, prompt, seed, resolution, "
         "classifier-free guidance (CFG) scale, a deterministic sampler, a scheduler and the step count T. Ancestral and "
         "stochastic samplers are excluded because their per-step noise is drawn on the executing GPU.")
    Para("The provider is rational and adaptive. It knows the protocol, the acceptance rules and the frozen thresholds, "
         "and it may choose any execution strategy that lowers its cost. It does not know before committing whether the "
         "job will be sampled or which steps will be checked, and in the core study it does not collude with verifiers. "
         "Table 2 lists the trust assumptions and the scope of the claims.")
    Table("Trust assumptions and claims of the core study",
          ["Item", "Treatment"],
          [["Trusted", "Escrow program; the sampling randomness (a delayed Solana slot hash); the verifier pool (honest, non-colluding); the orchestrator for liveness only"],
           ["Adversary", "Rational provider with a stable identity, knowledge of the rules, no advance knowledge of the sampling draw, and no collusion"],
           ["Claimed", "Consistency of the committed trajectory and output with the workflow under calibrated tolerances; detection probability; false rejection; verifier cost; on-chain cost and latency; deterrence under the stated payoff model"],
           ["Not claimed", "That a specific physical GPU executed the job; freshness against legitimate caching; prompt privacy; robustness to verifier collusion or Sybil attacks; production economics"]],
          [30, 138])

    H2("3-2- Verification Protocol")
    Para("A sampler with noise schedule σ{sub|0} > σ{sub|1} > … > σ{sub|T} produces latent states x{sub|0}, …, x{sub|T}, "
         "where x{sub|0} is the scaled initial noise and x{sub|T} the final latent. At step i it also produces the "
         "CFG-combined denoised prediction D{sub|i}. In ComfyUI the per-step callback exposes the pair (x{sub|i}, D{sub|i}) "
         "in the model’s internal latent space, so a custom node can record the full trajectory without operator-level "
         "instrumentation. Table 3 defines the evidence levels compared in this study, and Figure 2 shows the protocol.")
    Table("Evidence levels (T: number of steps; k: checked steps; c₀: fixed overhead relative to one step)",
          ["Level", "Provider commits", "Verifier checks when sampled", "GPU cost per job"],
          [["E0", "Image digest", "Full re-execution; pixel hash, LPIPS {c|zhang2018lpips} and DINOv2 {c|oquab2023dinov2} with calibrated thresholds", "≈ 1"],
           ["E0-N (deployed)", "Image", "Full re-execution; CLIP cosine > 0.9", "≈ 1"],
           ["E2-W (deployed)", "SHA-256 of per-step latents", "Three random steps, one step each; latent cosine ≥ 0.70", "≈ 3/T"],
           ["E1", "Merkle root over (x{sub|i}, D{sub|i}, σ{sub|i})", "Initial noise equals noise(seed) within u{sub|0}; schedule; conditioning; decoded final latent equals the image", "≈ c₀/T"],
           ["{b|E2-H (proposed)}", "As E1", "E1, plus Tier A on every step, plus Tier B at k random steps", "≈ (k + c₀)/T"]],
          [28, 38, 74, 28])
    Figure("F2", "Protocol overview: requester escrows P; provider (for example a rented RTX 5090) runs the workflow and commits the trajectory "
           "Merkle root; delayed slot hash decides sampling and the checked steps; verifier (DGX Spark) runs E1 checks, "
           "Tier A on all steps (CPU) and Tier B at k steps (GPU); verdict, two-of-three escalation, release, refund or "
           "slashing of bond B.", "Overview of the two-tier trajectory verification protocol with escrow settlement",
           image="fig2_protocol.png")
    Para("{b|Seed binding.} ComfyUI draws the initial noise on the CPU in 32-bit floating point from the job seed "
         "{c|comfyui}. The verifier recomputes it and compares it with x{sub|0}. Providers keep ComfyUI’s stock noise "
         "path. Because PyTorch’s vectorized normal sampler rounds differently on different processors and builds, the "
         "check accepts a largest absolute difference of at most u{sub|0}, measured in units of the unit-variance noise "
         "(the difference in x{sub|0} divided by σ{sub|0}). u{sub|0} is a fixed protocol constant, 10{sup|−5}, chosen "
         "so that it holds for any processor and PyTorch build without a per-build measurement: it lies well above the "
         "largest cross-processor rounding difference we measured (" + f"{RW.th_v1()['x0_p1_max_abs_observed']:.1e}" + ", between x86 and ARM CPUs) and far below the per-element differences "
         "of order one that a different seed produces, so it gives an attacker no usable freedom.")
    Para("{b|Reproducibility requirements.} Three sources of variation are fixed by the protocol rather "
         "than calibrated. First, the noise schedule σ{sub|0..T} is computed on the CPU from the model’s sampling "
         "parameters and passed to the sampler. ComfyUI otherwise computes it on whichever device holds the model, and "
         "a one-ULP difference in σ changes the whole trajectory. Second, the decisions that ComfyUI takes from the "
         "free memory at each call, namely whether the conditional and unconditional CFG passes share a batch and "
         "whether the VAE decodes in tiles, are pinned to a fixed choice during sampling, replay and decoding. "
         "Otherwise the same job could give a different trajectory depending on other workloads on the node. Both "
         "settings are recorded in the job metadata, which the Merkle root commits to. Third, providers and verifiers "
         "run one pinned software image, identified by its digest, so the PyTorch, CUDA and ComfyUI versions are fixed "
         "by the protocol rather than calibrated; the GPU driver, which the host controls, is recorded for every job.")
    Para("{b|Tier A: solver consistency on every step.} Given the committed values, the next state is a deterministic "
         "function of committed quantities only. For the Euler sampler:")
    Eq(omath(sub("x", "i+1"), ("p", "="), sub("x", "i"), ("p", "+"),
             frac(R(sub("x", "i"), ("p", "−"), sub("D", "i")), sub("σ", "i")),
             delim(R(sub("σ", "i+1"), ("p", "−"), sub("σ", "i")))))
    Para("For DPM-Solver++(2M) {c|lu2022dpmsolverpp}, with t{sub|i} = −log σ{sub|i}, h{sub|i} = t{sub|i+1} − t{sub|i} "
         "and r{sub|i} = h{sub|i−1}/h{sub|i}:")
    Eq(omath(sub("x", "i+1"), ("p", "="), frac(sub("σ", "i+1"), sub("σ", "i")), sub("x", "i"), ("p", "−"),
             delim(R(sup("e", R(("p", "−"), sub("h", "i"))), ("p", "−1"))),
             delim(R(delim(R(("p", "1+"), frac(("p", "1"), R(("p", "2"), sub("r", "i"))))), sub("D", "i"), ("p", "−"),
                     frac(("p", "1"), R(("p", "2"), sub("r", "i"))), sub("D", "i−1")), "[", "]")))
    Para("which reduces to the first-order update at the first and the final step. Tier A recomputes Equation 1 or 2 "
         "for all steps on the verifier’s CPU and compares the result to the committed x{sub|i+1} within a tolerance "
         "ε{sub|A} (0 for Euler, which is checked bit for bit), calibrated per sampler: the Euler update replicates bit for bit on a CPU, whereas "
         "DPM-Solver++(2M) takes step coefficients that ComfyUI computes on the GPU, so its replica differs in the last "
         "bits. It also checks that the committed schedule equals the schedule implied by the workflow, entry by entry "
         "within a fixed relative tolerance of 10{sup|−6} (the CPU-computed schedule differs by one unit in the last "
         "place between ARM and x86 processors), which catches step-count reduction directly. Tier A costs no GPU time. "
         "It rejects trajectories whose committed predictions do not match their states, such as a partial copy or "
         "interpolation whose D{sub|i} were left unchanged, at the boundary between computed and faked steps. It cannot "
         "reject a forger who derives D{sub|i} from the faked states by solving Equation 1, and it accepts a trajectory in "
         "which every step is copied, because D{sub|i} = x{sub|i} makes Equation 1 an identity. Detection of forgeries is "
         "therefore credited to Tier B; Tier A is a cheap filter.")
    Para("{b|Tier B: model consistency at random steps.} After the commitment is final, k distinct step indices are drawn "
         "from the sampling seed. For each checked step the verifier recomputes the CFG-combined prediction on its own GPU "
         "and accepts the step if the distance to the committed D{sub|i} is at most a per-step tolerance τ{sub|i} "
         "calibrated on honest cross-hardware runs; the distance is the relative L2 norm of the difference, fixed before any attack data. Per-step tolerances are needed because "
         "honest deviation varies with the noise level by about two orders of magnitude over the schedule (Figure 3).")
    Para("{b|Sampling, verdicts and settlement.} Each job is sampled with probability p using a Solana slot hash that "
         "exists only after the commitment is finalized and a fixed delay has passed, combined with the job identifier; "
         "the same draw seeds the checked steps. A fail or inconclusive verdict escalates to a second verifier and is "
         "decided by two-of-three agreement. A confirmed fail refunds the requester, forfeits the bond B and lowers the "
         "provider’s reputation. The verifier commits its recomputed values before the provider’s commitment is opened, "
         "so it cannot copy them. The trajectory, about " + (f"{RW.sizes()['full_mb']:.1f}" if RW.sizes() else "{R|R3.3}") + " MB per SDXL job, stays off-chain until the job closes; "
         "only the Merkle root and verdicts are recorded on-chain. An unsampled job transfers no trajectory data. Because "
         "Tier A reads every step, a sampled job sends the whole trajectory to the verifier; Tier B alone needs only the k "
         "opened steps with their Merkle inclusion proofs (" + (f"{RW.sizes()['kept_mb']:.1f} MB per job for eight opened steps" if RW.sizes() else "{R|R3.8}") + ").")

    H2("3-3- Analytical Model")
    Para("Let 𝒟{sub|H} be the distribution of what an output-only verifier observes under honest execution, including "
         "variation across the provider’s and verifier’s hardware, and 𝒟{sub|A} the distribution under attack A.")
    Para("{bi|Proposition 1 (output-only ceiling).} For any, possibly randomized, rule with false-rejection rate α, the "
         "sensitivity q{sub|A} to attack A satisfies Equation 3, independently of the sampling rate p:")
    Eq(omath(sub("q", "A"), ("p", "≤"), "α", ("p", "+"), ("p", "TV"), delim(R(sub("𝒟", "A"), ("p", ","), sub("𝒟", "H")))))
    Para("{i|Proof.} For any event E, the probabilities of E under 𝒟{sub|A} and 𝒟{sub|H} differ by at most their "
         "total-variation distance (TV); take E as the event that the rule returns fail, and condition on the rule’s "
         "random coins for randomized rules. The sampling rate changes how many jobs are examined, not this probability. "
         "∎ Raising p therefore cannot rescue an output-only rule against an attack whose outputs overlap honest ones; "
         "richer evidence helps exactly when it increases the total-variation distance.")
    Para("{bi|Proposition 2 (spot-check detection).} Suppose a provider fakes m = sT steps so that Tier A passes, and "
         "Tier B checks k steps drawn uniformly without replacement. Let r be the probability that a faked step exceeds "
         "its tolerance and α{sub|s} the probability that an honest step does. Assuming independent per-step outcomes, a "
         "sampled faked job fails Tier B with the probability in Equation 4, and an honest job with the probability in "
         "Equation 5:")
    Eq(omath(("p", "q"), delim(("p", "s,k")), ("p", "=1−"),
             nsum(("p", "x=0"), "k", R(frac(R(binom("m", "x"), binom(R("T", ("p", "−"), "m"), R("k", ("p", "−"), "x"))), binom("T", "k")),
                                       sup(delim(R(("p", "1−"), "r")), "x"),
                                       sup(delim(R(("p", "1−"), sub("α", "s"))), R("k", ("p", "−"), "x"))))))
    Eq(omath("α", delim("k"), ("p", "=1−"), sup(delim(R(("p", "1−"), sub("α", "s"))), "k")))
    Para("{i|Proof.} The number of faked steps among the checked ones is hypergeometric. Given that x of them are "
         "checked, the job passes only if all x faked and all k − x honest checked steps pass, with probabilities "
         "(1 − r){sup|x} and (1 − α{sub|s}){sup|k−x}. ∎ For large T, q(s,k) ≈ 1 − (1 − sr − (1 − s)α{sub|s}){sup|k}. A "
         "corollary is that keeping the job-level false-rejection rate at or below α* requires the per-step tolerance of "
         "Equation 6, so checking more steps requires a stricter per-step tolerance; with k = 3 and α* = 1%, each step "
         "may falsely reject at most about 0.33% of the time.")
    Eq(omath(sub("α", "s"), ("p", "≤1−"), sup(delim(R(("p", "1−"), sup("α", ("p", "*")))), R(("p", "1/"), "k"))))
    Para("{bi|Proposition 3 (all-or-nothing best response).} Let an honest job cost the provider c in GPU time, let "
         "faking a fraction s of the steps save β{sub|A}sc, where β{sub|A} ≤ 1 is the share of cost avoided, and let a "
         "detected fraud forfeit L = P + B. Neglecting reputation, the expected gain from cheating relative to honesty is "
         "given by Equation 7. Under the large-T approximation, Δ(s) is convex on [0, 1], so the best response is "
         "s* ∈ {0, 1}, and cheating is deterred, that is Δ(s) ≤ 0 for all s, if and only if Equation 8 holds:")
    Eq(omath("Δ", delim("s"), ("p", "="), sub("β", "A"), "s", "c", ("p", "−"), "p",
             delim(R("q", delim(("p", "s,k")), ("p", "−"), "α", delim("k")), "[", "]"), "L"))
    Eq(omath("p", delim(R(("p", "1−"), sup(delim(R(("p", "1−"), sub("r", "A"))), "k"), ("p", "−"), "α", delim("k")), "[", "]"),
             delim(R("P", ("p", "+"), "B")), ("p", "≥"), sub("β", "A"), "c"))
    Para("{i|Proof.} With u = sr + (1 − s)α{sub|s}, which is affine in s, q = 1 − (1 − u){sup|k} is concave in s for "
         "k ≥ 1, so −pqL is convex and adding the linear saving keeps Δ convex. A convex function on an interval attains "
         "its maximum at an endpoint; since Δ(0) = 0, deterrence holds if and only if Δ(1) ≤ 0, which is Equation 8. ∎ "
         "Equation 8 must hold for every attack class in scope. The marketplace minimizes the expected verifier cost per "
         "job, p(k + c₀)c/T, subject to Equation 8; for a fixed k the smallest feasible sampling rate is given by "
         "Equation 9, and the best k follows from a one-dimensional search. Attacks with r{sub|A} ≈ α{sub|s} make "
         "Equation 9 infeasible for every k, which is the step-level analogue of Proposition 1. The quantities r{sub|A} "
         "and β{sub|A} are estimated in RQ2, and Equations 4 and 8 are tested in RQ3.")
    Eq(omath(sup("p", ("p", "*")), delim("k"), ("p", "="),
             maxover("A", frac(R(sub("β", "A"), "c"),
                               R(delim(R(("p", "1−"), sup(delim(R(("p", "1−"), sub("r", "A"))), "k"), ("p", "−"), "α", delim("k")), "[", "]"),
                                 delim(R("P", ("p", "+"), "B")))))))

    H2("3-4- Experimental Design")
    Para("{b|Hardware.} Owned hardware comprises six NVIDIA DGX Spark systems (Blackwell GB10, ARM64 processor, unified "
         "CPU and GPU memory). They were shared with other inference workloads during the study. All x86-64 GPUs are "
         "rented by the hour from a commercial GPU cloud (RunPod; RTX 3090, RTX 4090 and RTX 5090): consumer GeForce RTX cards of the "
         "Blackwell, Ada and Ampere generations. A rented node runs the same pinned software in a container, but its driver is set by the "
         "host, so the driver version and the hourly price of each rented node are recorded. Results that depend on "
         "timing are measured only on rented GPUs, which a job has to itself. Table 4 defines the five nested heterogeneity levels; "
         "driver, CUDA, PyTorch and ComfyUI versions of every node are recorded in each run manifest.")
    Table("Nested heterogeneity levels",
          ["Level", "Comparison", "Isolates"],
          [["L0", "Same unit, repeated runs", "Run-to-run nondeterminism"],
           ["L1", "Same unit, different software configuration", "Precision, attention implementation, deterministic mode"],
           ["L2", "Two units of the same model", "Unit-to-unit variation"],
           ["L3", "Rented x86 Blackwell GPU versus DGX Spark", "Chip, compute capability, memory system, processor instruction set"],
           ["L4", "Blackwell versus Ampere and Ada (rented)", "GPU generation"]],
          [18, 70, 80])
    Para("{b|Workloads.} SD1.5 {c|rombach2022ldm} at 512 × 512 and SDXL {c|podell2023sdxl} at 1024 × 1024 pixels are run "
         "with 30 steps, the Euler and DPM-Solver++(2M) samplers and a fixed CFG scale, in ComfyUI at a pinned commit. "
         "Prompts are drawn from PartiPrompts {c|yu2022parti} (Apache-2.0 licence), sampled with a fixed random seed. Each prompt is run with three seeds, "
         "and prompts are split into calibration (400 prompts), development (200) and test (400) sets. On the DGX Spark systems the full factor grid "
         "is run: precision (fp16, bf16, and fp32 for SD1.5 only) × attention implementation (two options) × sampler (two) × deterministic "
         "mode (off, on). SDXL in fp32 is excluded: in the pilot it filled the whole memory of the 24 GB and 32 GB rented cards and could not run beside other workloads on a DGX Spark. "
         "Rented GPUs run the reference configuration and the precision factor; one rented x86 GPU of the Ada "
         "generation also runs the deterministic-mode and attention factors at fp16. The reference "
         "configuration (fp16, default attention, both samplers, deterministic mode off) is the one for which tolerances "
         "are frozen. It is run on a larger prompt set than the other configurations, because the per-step tolerances "
         "of Equation 6 are extreme quantiles of the honest distribution: on the DGX Spark systems it runs all 600 "
         "calibration and development prompts, and on each rented card 300 of them plus 200 test prompts, so that each "
         "card is rented once. Every other configuration runs the same 50 prompts (32 calibration, 18 development) on "
         "every node, so each factor level is compared on the same 150 jobs. Level L0 repeats 10% of the reference "
         "jobs on one DGX Spark; level L2 runs 50 prompts in the reference configuration on all six DGX Spark systems "
         "and on two RTX 5090 cards on different hosts.")
    Para("{b|Pilot.} A pilot fixed the design choices above before the study runs. It used three DGX Spark systems and "
         "rented RTX 5090 (Blackwell), RTX 4090 (Ada) and RTX 3090 (Ampere) cards, SDXL and SD1.5 at 30 steps, and "
         "prompts from the calibration split only, so none of its jobs enters the test split. Trajectories were "
         "bit-identical between two DGX Spark units (40 of 40 SDXL jobs with either sampler) and under co-located GPU "
         "load (60 of 60 jobs in each of four load and batching conditions), whereas no pair of different GPU models "
         "produced a single bit-identical image (0 of 40 SDXL jobs for each of the six pairs). The initial noise fell "
         "into an ARM and an x86 family, identical within each family and at most 2.3 × 10{sup|−6} apart between them, "
         "which sets the scale for u{sub|0}. When a DGX Spark replayed the steps of the three x86 providers (40 jobs "
         "each), Tier A reproduced all 3,600 Euler steps bit for bit, whereas for DPM-Solver++(2M) its CPU replica "
         "matched only 560 of 1,200 steps even between two DGX Spark units with identical trajectories; hence ε{sub|A} "
         "is set per sampler. The median relative L2 distance between recomputed and committed D{sub|i} fell from "
         "2.7–2.9% at the first step to 0.04% at the last, for all three providers; hence τ{sub|i} is set per step. On "
         "every rented card, the fp8 and NVFP4 paths of the pinned ComfyUI commit were slower than fp16 (NVFP4 runs "
         "only through a dequantizing fallback). Attacks A2 and A2b therefore save the provider no GPU time at this "
         "commit (β{sub|A} ≤ 0, so Equation 8 holds for them trivially) and are kept as detection cases.")
    Para("{b|Attacks and forgeries.} Table 5 lists the attack set of the design. The attack study reported here "
         "evaluates the subset marked in the table, for SDXL with the Euler sampler in the reference configuration, "
         "with a rented RTX 5090 as provider and DGX Spark systems as verifiers, which is the direction of a "
         "marketplace where consumer cards serve jobs: 100 attacked jobs per attack on the test split, the same jobs "
         "for every attack. Partial faking is evaluated with F3 at five faked fractions s. The saving β{sub|A} is "
         "measured, not assumed, on the rented GPU, which the job has to itself, against an honest run of the same "
         "jobs.")
    Table("Attacks and forgeries (β{sub|A}: measured share of GPU time saved, median over the same jobs generated honestly on the same card; * evaluated in this study)",
          ["ID", "Attack", "Implementation", "Saving β{sub|A}"],
          [["A1*", "Fewer steps", "25, 20 or 15 steps with the schedule relabelled as 30 (evaluated: 20 steps)", RW.table5_beta("A1b")],
           ["A2*", "fp8 denoising network", "ComfyUI flag --fp8_e4m3fn-unet", RW.table5_beta("A2")],
           ["A2b", "4-bit (NVFP4) model", "NVFP4 checkpoint; at the pinned commit it runs only through a dequantizing fallback", "not evaluated"],
           ["A3*", "Distilled model", "SDXL-Turbo, LCM-LoRA or Lightning (evaluated: Turbo, 4 steps; LCM-LoRA, 6 steps)", "Turbo " + RW.table5_beta("A3-Turbo") + "; LCM " + RW.table5_beta("A3-LCM")],
           ["A4", "Sampler swap", "Cheaper sampler committed as the required one", "not evaluated"],
           ["A5", "Low resolution + upscale", "Generation at half resolution, then upscaling", "not evaluated"],
           ["A6", "Early exit", "Truncation, then extrapolation", "not evaluated"],
           ["A7", "Replay", "Output of a near-duplicate prompt", "not evaluated"],
           ["A8*", "Unrelated output", "Sanity control", RW.table5_beta("A8")],
           ["F1*", "Frame copy", "Each faked state copies the previous one", RW.table5_beta("F1")],
           ["F2*", "Interpolation", "Linear interpolation between computed anchor steps", RW.table5_beta("F2")],
           ["F3*", "Solver inversion", "Compute m steps; solve Equation 1 for the remaining D{sub|i}", RW.table5_beta("F3")],
           ["F4", "Cheap-model trajectory", "Complete, consistent trajectory from A2 or A3", "not evaluated"],
           ["M*", "Falsified metadata", "Negative control", RW.table5_beta("M")]],
          [14, 40, 90, 24])
    Para("{b|Calibration and statistics.} All tolerances are chosen on the calibration split: pixel, LPIPS and DINOv2 "
         "thresholds for E0, ε{sub|A} for Tier A, and τ{sub|i} for Tier B, set by Equation 6 for α* = 1%, separately "
         "for each model and sampler. The Tier B distance is the relative L2 distance between recomputed and committed "
         "D{sub|i}, fixed from the pilot before any attack data was generated; the maximum absolute difference and the "
         "cosine distance are reported as secondary measures. The honest "
         "per-step distances for τ{sub|i} come from cross-hardware replays: a DGX Spark acting as verifier recomputes "
         "D{sub|i} at every step of each rented provider’s calibration jobs, so every step and every provider–verifier "
         "pair contributes; τ{sub|i} pools the pairs and falls back to the largest pair quantile when one pair deviates "
         "by more than a factor of two. Tolerances are set separately for each sampler. They are frozen "
         "with a recorded hash before any attack data is examined. Error rates are reported on the disjoint test split with "
         "Wilson 95% confidence intervals {c|wilson1927}; medians and costs use cluster-bootstrap intervals over prompt and "
         "hardware pair. Zero false rejections in 299 independent honest audits bound the false-rejection rate below 1% at "
         "95% confidence, which sets the minimum number of honest test jobs per stratum. The target is 1,000 honest test "
         "jobs per stratum, which keeps the same bound with up to four false rejections, and 100 attacked jobs per "
         "attack, model and hardware pair.")
    Para("{b|Data retention.} Full trajectories are kept where an analysis needs every step: the reference "
         "configuration and levels L0 and L2 on the DGX Spark systems, the calibration and development prompts of the "
         "reference configuration on every rented card, and the jobs of the partial-faking sweep. The other "
         "configurations of the DGX Spark grid, the test prompts and the attacked jobs on rented GPUs keep opened "
         "steps only, and the precision and factor-slice runs on rented GPUs keep the image, the final latent, the "
         "Merkle root and the result of Tier A. For opened steps, eight steps per job are drawn before generation from "
         "a committed seed that the "
         "attack implementations never see, and only those steps, their Merkle inclusion proofs, the job metadata, the "
         "image and the result of Tier A, computed over all steps on the rented host before the trajectory is "
         "discarded, are kept. The drawn sets are nested, so one draw serves every k ≤ 8. This is the information a "
         "deployed verifier receives, and it keeps the transfer from rented hosts within the budget.")
    Para("{b|Testbed.} Rented consumer GPUs act as providers and DGX Spark systems as verifiers. The escrow program runs on a "
         "local validator on a rented x86 host for volume and on the Solana Devnet for fees and latency. For each lifecycle path (accepted, "
         "sampled and passed, sampled and disputed, timeout refund) signature counts, compute units, fees and latency to "
         "the processed, confirmed and finalized commitment levels are reported {c|solana_fees}. The Solana mainnet is "
         "not used. Mainnet fees are calculated from the measured signature counts and compute units at a dated SOL "
         "price, and are labelled as calculated. Verifier GPU time is also converted to US dollars at the recorded "
         "rental prices. Scale-out beyond the physical nodes is "
         "evaluated by a Monte Carlo simulation of Propositions 2 and 3 using the measured r{sub|A}, α{sub|s} and β{sub|A}. "
         "For each attack and each combination of sampling rate p, checked steps k, bond ratio B/P and faked fraction s, "
         "simulated providers fake sT steps, the checked steps are drawn without replacement, and each checked step "
         "fails with probability r{sub|A} if faked and α{sub|s} if honest. The simulation compares the empirical "
         "detection rate with Equation 4 and estimates the mean gain Δ(s) of Equation 7 with a bootstrap confidence "
         "interval, from a recorded random seed. Testbed jobs with injected attackers give an independent "
         "check of the deterrence region at three sampling rates. {R|NEEDS WORK: the testbed demo (runbook §7 item 5) "
         "has not been run; run it or remove this sentence}")

    # ================================================================== 3 RESULTS AND DISCUSSION
    H1("4- Results and Discussion")
    H2("4-1- Honest Variation (RQ1)")
    fac = RW.r1_factors()
    steps = RW.r1_steps()
    Para("{b|Exact reproducibility.} Table 6 reports the share of jobs whose final images are bit-identical across "
         "two runs of the same workflow, by heterogeneity level. On one unit (L0) and across different units of the same "
         "GPU model (L2), every image was bit-identical for both models and both samplers. Across chips of the same "
         "generation (L3, DGX Spark and RTX 5090) and across generations (L4, RTX 3090 and RTX 4090 against the "
         "Spark), no image was bit-identical. Bit-exact reproduction is therefore available only within one GPU model, "
         "which a permissionless marketplace cannot enforce.")
    Table("Share of bit-identical final images (%) by level (number of run pairs; number of compared jobs), "
          "pooled over the fp32, fp16 and bf16 profiles",
          ["Model, sampler", "L0 (same unit)", "L2 (same model)", "L3 (same generation)", "L4 (across generations)"],
          RW.r1_identity(), [44, 30, 30, 32, 32])
    Para("{R|NEEDS WORK: Table 6 has no SDXL run at L0 and no SDXL DPM++ 2M run at L2 or L3, which Section 3-4 plans; run them or narrow the design text}")
    if fac:
        f = {k: v for k, v in fac.items()}
        Para("{b|Factors.} On one unit (L1), changing the numeric precision ("
             + (f"{RW.pc(f['precision'][0], 0)}% identical over {f['precision'][2]:,} jobs" if 'precision' in f else "") +
             ") or the attention implementation ("
             + (f"{RW.pc(f['attention'][0], 0)}% over {f['attention'][2]:,} jobs" if 'attention' in f else "") +
             ") changed every image, whereas enabling PyTorch's deterministic mode did not change any image ("
             + (f"{RW.pc(f['deterministic'][0], 0)}% identical over {f['deterministic'][2]:,} jobs" if 'deterministic' in f else "") +
             "). The software profile is thus a first-order factor, and pinning it is a precondition for any "
             "tolerance; deterministic mode alone neither helps nor hurts reproducibility on a given unit.")
    if steps:
        n = sorted({v["n_jobs"] for v in steps.values()})
        Para("{b|Per-step deviation.} Figure 3 shows the per-step Tier B distance between the provider's committed "
             "denoised prediction D{sub|i} and the Spark verifier's replay for the three SDXL Euler calibration pairs "
             f"({n[0]} calibration jobs per pair). The honest deviation falls by about two orders of magnitude from the "
             "first to the last step and is nearly the same for the L3 and the two L4 pairs, so a single "
             "per-step tolerance profile serves all three; a constant tolerance would be either too loose at late "
             "steps or too tight at early ones. The frozen τ{sub|i} lie, by construction, at the 99th percentile of "
             "these calibration distances.")
    Figure("R1.4", "", "Honest per-step deviation (SDXL, Euler) for each provider → verifier pair, calibration "
           "split, with the frozen per-step tolerance τ_i for k = 1", image="fig_r1_4_steps.png" if steps else None)
    Para("{b|Answer to RQ1.} Honest outputs are bit-identical only within one GPU model under one pinned software "
         "profile. Across chips and generations no output is identical, but the per-step deviation is small, smooth "
         "in the step index and nearly independent of the hardware pair, which is what makes calibrated per-step "
         "tolerances possible.")

    H2("4-2- Separating Attacks from Honest Variation (RQ2)")
    Para("{b|Honest jobs and the E1 image tolerance.} On the 1,800 honest test jobs, Tier A rejected no job, and the "
         "deployed rules accepted almost all of them (Table 7). Under the frozen thresholds v1, however, E1 rejected "
         "every honest RTX 3090 and RTX 4090 job and 2.3% of the RTX 5090 jobs, all for one reason: the decoded "
         "x{sub|final} differed from the delivered image by more than the image tolerance of 2 uint8 levels, a "
         "development constant that had never been calibrated. Because E2-H includes E1, its honest false-rejection "
         "rate was about 68% under v1. We therefore calibrated this one tolerance after the freeze (thresholds v2), on "
         "the calibration split only and with the rule fixed before measuring (twice the largest honest difference, "
         "as for ε{sub|A}). The largest honest difference was 132 levels (RTX 4090), 79 (RTX 3090) and 63 (RTX 5090); "
         "the rule gives 264, above the 255 range, so under v2 the image comparison never rejects and E1 reduces to "
         "its x{sub|0}, schedule and conditioning checks. A per-pixel maximum cannot bind the delivered image to the "
         "trajectory across architectures; a statistic over the whole image would be needed. Both versions are "
         "reported; v2 is a post-freeze correction of one parameter and is labelled as such.")
    Para("{b|Deployed rules.} Table 7 reports the acceptance rate of the reproduced deployed rules under each attack. "
         + RW.narr_r21())
    Table("Acceptance rate (%, 95% Wilson CI) of the deployed rules, SDXL Euler, test split; attacks on a rented "
          "RTX 5090, 100 jobs each; verifier DGX Spark",
          ["Condition", "E0-N (CLIP cosine > 0.9)", "E2-W (latent cosine ≥ 0.70)"],
          RW.table_deployed(), [70, 49, 49])
    Para("{b|Calibrated evidence levels.} Table 8 reports the share of attacked jobs rejected (sensitivity q) by each "
         "calibrated evidence level at the frozen thresholds, with the honest false-rejection rate of the same level on "
         "the 1,800 test jobs in the last row. " + RW.narr_r23() + " Both realised honest rates exceed their targets: "
         "the 1.2% of E2-H lies above the 1% its per-step tolerances were set for, which is consistent with the "
         "sampling error of a 99th-percentile tolerance estimated from the calibration split, and the 3.3% of E0 lies "
         "above the 1% its thresholds were set for. The E0 gap has two parts. First, E0 passes a job only if both "
         "LPIPS and DINOv2 lie within their 99% bounds, and the two exceedances overlap only partly, so even on the "
         "calibration split it rejected 1.4% of honest jobs. Second, on the test split each metric was exceeded about "
         "twice as often, on all three rented cards (LPIPS 2.0% and DINOv2 2.2%, against 1.0% each). Re-splitting the "
         "400 calibration and test prompts at random 2,000 times gave a held-out rate between 0.8% and 2.9% in 95% of "
         "splits, and 3.3% or more in 0.8%, so prompt sampling alone is an unlikely explanation. The test failures "
         "concentrate on jobs that fail against all three cards (6 jobs, against 1 on the calibration split), which "
         "points to the DGX Spark reference images, regenerated for the test split in a separate run, or to a few "
         "prompts. {R|NEEDS WORK: regenerate some calibration jobs with the test-split reference procedure and compare "
         "them bit for bit with the calibration references, to tell the two causes apart} {R|NEEDS WORK: the F1–F3 rows of Tables 7 and 8 come from forgeries of an honest trajectory "
         "(see Partial faking) and will change when F1–F3 are regenerated}")
    Table("Share of attacked jobs rejected (%, 95% Wilson CI) by evidence level at the frozen thresholds; last row: "
          "honest false-rejection rate. v1: thresholds as frozen; v2: E1 image tolerance recalibrated (post-freeze)",
          ["Attack", "E0", "E1 (v1)", "E1 (v2)", "E2-H, k = 1 (v1)", "E2-H, k = 1 (v2)", "E2-H, k = 8 (v2)"],
          RW.table_sensitivity(), [38, 21, 21, 21, 22, 22, 22])
    part = RW.sweep_tiers()
    Para("{b|Partial faking.} " + RW.narr_r27())
    Figure("R2.7", "Measured q(s,k) under partial faking (F3 with varying s) against Equation 4 with the measured r and "
           "α_s.", "Spot-check detection under partial faking (F3, generated on a DGX Spark): measurement with 95% "
           "Wilson intervals; solid lines: Equation 4 with m = sT, r = 1 and the measured α_s; dashed: Equation 4 with m = the "
           "measured number of steps above τ_i per job",
           image="fig_r2_7_partial.png" if part else None)
    Para("{b|Per-step separability and cost share.} Table 9 gives, for each attack, the per-step separability r{sub|A} "
         "(the share of faked checked steps whose distance exceeds τ{sub|i}), the share of GPU time the attack saves "
         "β{sub|A}, and the smallest sampling rate p* that deters it by Equation 9. β{sub|A} compares each attacked job "
         "with the same job generated honestly on the same rented RTX 5090 (the first job of each run is a warm-up and is "
         "dropped). For F1–F3 the attack harness generates the honest trajectory before forging part of it, so its "
         "timing does not measure what a forger saves; their β{sub|A} is bounded by the faked share s and p* uses that "
         "bound. A2 ran slower than honest generation on this card (fp8 weights are converted at run time), as in the "
         "pilot. The negative β{sub|A} of A1b and of the control M, however, are a measurement artefact: the attacked "
         "jobs were timed over the whole attack harness, including forging and hashing, and the honest jobs over "
         "sampling only, so M, which computes honestly, appears 13% slower. " + '{R|NEEDS WORK: β_A must be re-measured on the same timing field for attack and honest jobs}. ' + RW.narr_r28())
    Table("Per-step separability r_A (k = 1, %, 95% CI), cost share β_A (median, 95% bootstrap CI) and the deterring "
          "sampling rate p* of Equation 9 at c/P = 1 (p* scales linearly with c/P)",
          ["Attack", "r_A (%)", "β_A", "p*, k = 1, B/P = 0", "p*, k = 1, B/P = 1", "p*, k = 3, B/P = 1"],
          RW.table_deterrence(), [44, 26, 24, 24, 24, 24])
    Para("{b|Answer to RQ2.} " + RW.narr_r29())

    H2("4-3- Cost and Deterrence (RQ3)")
    vc = RW.verifier_cost()
    Para("{b|Verifier cost.} Table 10 gives the GPU time of each evidence level on the rented RTX 5090, which a job has "
         "to itself (DGX Spark timings are not used because the systems are shared). "
         + (f"Replaying all {vc['T']} steps of a job took {vc['replay_all_median']:.2f} s (median over {vc['n_replay']} "
            f"jobs), and the replay on the same card was bit-exact for {RW.pc(vc['exact_share'], 0)}% of the jobs and "
            "steps, as expected at L0. " if vc.get("replay_all_median") else "")
         + "Tier B at k steps costs k/T of a full replay, so a spot check of one to three steps costs a small fraction "
           "of E0's full regeneration.")
    Table("Verifier GPU time per job on the rented RTX 5090 (SDXL, 1024², Euler, 30 steps)",
          ["Evidence level", "GPU-seconds (median)", "Relative to E0"], RW.table_verifier_cost(), [86, 40, 40])
    n, f, fc, tx = RW.escrow_failures()
    Para("{b|Escrow cost.} Table 11 gives the measured cost of each lifecycle path of the escrow program on Solana "
         f"Devnet, over 100 successful jobs per path ({tx:,} transactions). Fees are the base fee of 5,000 lamports per "
         "signature; on mainnet the same base fee applies and priority fees, which were not measured, come on top. "
         f"Of {n} jobs started, {f} failed at the RPC layer ({fc} during a known network change of the client), "
         "none in the program.")
    Table("Escrow cost per lifecycle path on Solana Devnet (100 successful jobs per path)",
          ["Path", "Compute units per job (median)", "Fee on Devnet (SOL per job)", "Fee on mainnet (SOL, calculated)",
           "Time to confirmed per transaction (median, p95)"],
          RW.escrow(), [40, 32, 28, 34, 34])
    Para("{b|Monte Carlo.} " + RW.narr_mc())
    Para("{b|Answer to RQ3.} " + RW.narr_r32() + " The escrow adds a fixed on-chain cost per job (Table 11) that does not "
         "depend on the evidence level.")

    H2("4-4- Discussion")
    Para("{b|What the blockchain adds.} Integrity detection in this design does not depend on the chain: a trusted "
         "broker running the same checks would detect the same attacks. The escrow makes the payoff model of Proposition 3 "
         "enforceable without a custodian, because payment and bond are locked before execution, released or forfeited by "
         "recorded verdicts, and refunded on timeout if the orchestrator fails. Its cost on Devnet was 15,000 to 50,000 lamports in fees and 63,000 to 125,000 compute units per job, depending on the path (Table 11).")
    Para("{b|Implications for marketplaces.} Four practical rules follow from the measurements. First, pin the software "
         "profile: precision and attention implementation each changed every image on one unit, so a tolerance calibrated "
         "for one profile says nothing about another. Second, never ship an uncalibrated tolerance: the 2-level image "
         "constant of E1 alone rejected every honest cross-architecture job, and the deployed cosine thresholds accepted "
         "unrelated work. Third, calibrate per step against a job-level false-rejection target on held-out honest "
         "cross-GPU pairs, and check the realised rate on a test split. Fourth, commit the full trajectory and check "
         "solver consistency on every step on the CPU: it is cheap and rejects careless forgeries, but a forger who "
         "computes its steps from its own forged states, or re-solves D{sub|i} with exact rounding, passes it, so the "
         "spot check of Tier B carries the detection.")
    Para("{b|Relation to operator-level verification and to language models.} Sampler-level evidence and the "
         "operator-level evidence of TAO {c|yao2026tao} are complementary: where Tier B cannot separate an attack "
         "(" + RW.inseparable() + "), operator-level commitments or trusted execution {c|slalom2019} are required. For LLM inference, output-only detection "
         "of quantized substitution is already known to fail {c|cai2025substitution}, and activation-based schemes apply, "
         "so LLM workloads are not evaluated here.")
    Para("{b|Responsible disclosure.} The deployed rules were reproduced from public source code at fixed commits and "
         "attacked offline only. {T|record the disclosure to the subnet operators and their response}.")
    Para("{b|Limitations.} The attack study is reduced in scope: SDXL with the Euler sampler only, one provider → verifier "
         "direction (rented RTX 5090 → DGX Spark) and nine attack conditions of 100 test jobs each; A2b, A4–A7 and F4 were not "
         "run, and SD1.5 and DPM++ 2M were not attacked. One tolerance, the E1 image tolerance, was corrected after the "
         "freeze (v2, calibration split only, rule fixed before measuring), and both versions are reported. The verifier pool is assumed honest and non-colluding; incentive mechanisms for verifiers "
         "and counter-collusion contracts {c|luu2015,dong2017} are complementary. Cross-generation results cover only the models "
         "tested (SD1.5 and SDXL on RTX 3090, RTX 4090, RTX 5090 and DGX Spark), from the Ampere, Ada and Blackwell generations; earlier generations were not tested. Deterministic samplers are required. Proposition 3 uses the large-T approximation and "
         "independent per-step outcomes, which are checked empirically (Figure 4). Reputation is not modelled in Equation "
         "7. Mainnet fees are calculated, not measured, and mainnet latency, priority-fee behaviour and transaction "
         "landing rate were not measured. The DGX Spark systems were shared with other workloads, so no timing result comes from "
         "them. For rented providers, test and attacked trajectories were kept only at eight pre-drawn steps, so the "
         "partial-faking analysis and any check with k > 8 use jobs generated on the DGX Spark systems. "
         "The full grid of software factors was measured on that one GPU platform, and on x86 only the precision, "
         "deterministic-mode and attention factors were measured. All results hold for the one pinned software stack; "
         "tolerances calibrated on it are not claimed to cover other PyTorch or CUDA versions, which is why the protocol "
         "pins the image. Under thresholds v2 the delivered image is not bound to the committed trajectory, so a "
         "provider could deliver an image other than the one its trajectory produces; closing this gap needs a "
         "whole-image statistic. Finally, re-execution establishes consistency with the committed "
         "workload, not that a particular GPU performed it.")

    # ================================================================== 4 CONCLUSION
    H1("5- Conclusion")
    Para("This study asked what evidence a decentralized GPU marketplace must demand to detect cost-saving cheating on "
         "diffusion jobs, and at what cost. Honest outputs were bit-identical only within one GPU model under one pinned "
         "software profile, so every cross-hardware rule needs a tolerance (RQ1). " + RW.narr_r29() + " (RQ2). "
         + RW.narr_r32() + " (RQ3). For marketplaces, the recommendation is to require the committed trajectory, an "
         "all-step solver check on the CPU and a calibrated spot check of one to three steps, settled through an escrow "
         "with a bond. Future work should extend the attack study to more models, samplers and provider–verifier "
         "directions, replace the per-pixel image binding with a statistic that holds across architectures, and add "
         "resistance to colluding verifiers.")

    # ================================================================== 5 DECLARATIONS
    H1("6- Declarations")
    H2("6-1- Author Contributions")
    Para("Conceptualization, A.R.M.; methodology, A.R.M. and D.E.C.; software, E.R.; validation, E.R.; formal "
         "analysis, D.E.C.; investigation, E.R.; resources, E.R.; data curation, E.R.; writing—original draft "
         "preparation, D.E.C.; writing—review and editing, A.R.M., E.R. and P.Y.; visualization, D.E.C.; supervision, "
         "P.Y.; project administration, A.R.M. All "
         "authors have read and agreed to the published version of the manuscript.", "decl")
    H2("6-2- Data Availability Statement")
    Para("The data presented in this study are openly available in the GitHub repository https://github.com/ditoec/decentralized-research, archived at {R|R0.2: Zenodo DOI}. They "
         "include code, workflow fingerprints, frozen thresholds, trajectories (or a sample, if storage limits apply) and "
         "checksums.", "decl")
    H2("6-3- Funding")
    Para("{T|state funder, award number and grant recipient, or:} Funding information is not available.", "decl")
    H2("6-4- Acknowledgements")
    Para("{T|acknowledgements, up to 100 words; include the statement on AI-assisted writing and editing if required by "
         "the journal}", "decl")
    H2("6-5- Institutional Review Board Statement")
    Para("Not applicable.", "decl")
    H2("6-6- Informed Consent Statement")
    Para("Not applicable.", "decl")
    H2("6-7- Conflicts of Interest")
    Para("{T|E.R. is the founder of Vektor Labs: declare any commercial interest in GPU marketplaces or verification, "
         "or confirm none} The authors declare that there is no conflict of interests regarding the publication of this manuscript. In "
         "addition, the ethical issues, including plagiarism, informed consent, misconduct, data fabrication and/or "
         "falsification, double publication and/or submission, and redundancies have been completely observed by the "
         "authors.", "decl")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
