# Datasets字段策略对比分析
生成时间: 2026-07-03T14:24:26.694637
## 策略概览
| 策略 | Recall | Precision | F1 | Gold数据集 | 提取数据集 | 匹配数 | 漏抽数 | 多抽数 | 平均耗时(ms) |
|------|--------|-----------|----|-----------|-----------|-------|-------|-------|-----------|
| datasets--策略v1--Section+Table提取 (Layer 2) | 9.88% | 66.67% | 17.20% | 81 | 12 | 8 | 73 | 4 | 0.0 |
| datasets--策略v2--关键词全文匹配 (Layer 1) | 29.63% | 7.59% | 12.09% | 81 | 316 | 24 | 57 | 286 | 0.0 |
| datasets--策略v3--Gazetteer验证 (强语境正则+白名单+黑名单) | 7.41% | 26.09% | 11.54% | 81 | 23 | 6 | 75 | 17 | 341.8 |

## V3 预处理统计
- 平均总耗时: 341.76 ms
- P95 总耗时: 768.93 ms
- 平均strip_references耗时: 0.00 ms
- 平均section_select耗时: 0.00 ms
- 平均candidate_extract耗时: 139.24 ms
- 平均gazetteer_match耗时: 191.95 ms
- 平均blacklist_filter耗时: 0.07 ms

### Strip References 方法分布
- none: 7 篇

## 漏抽案例

### datasets--策略v1--Section+Table提取 (Layer 2)
- 漏抽论文数: 9
  - 5b1643ba8fbcbf6e5a9bc884: 漏抽 41 个 (['ar', 'cplfw', 'rfw', 'guoetal.', 'casiafasd', 'nirvis2.0', 'fam', 'celebfaces+', 'replayattack', 'casiahfb', 'casiawebface', 'calfw', 'frgcv2', 'vggface2', 'cufs', 'lfw', 'facebook', 'sllfw', 'feret', 'cfp', 'asianceleb', 'ytf', 'bosphorus', 'webcaricature', 'google', 'cufsf', 'umdfacesvideos', 'ijba', 'morph', 'msv1c', 'bu3dfe', 'msceleb1m', 'megaface', 'delfw', 'pasc', 'dfw', 'umdfaces', 'elfw', 'ijbc', 'vggface', 'ijbb'])
  - 627c6cfe5aee126c0f83214c: 漏抽 4 个 (['audioset', 'msrvtt', 'wavcaps', 'mscoco'])
  - 6632f3d201d2a3fbfc5b36bb: 漏抽 2 个 (['jaad', 'psi'])
  - 63b63fca90e50fcafd8f4461: 漏抽 7 个 (['marsv2', 'suhifimask', 'replayattack', 'casiamfsd', 'siw', 'hifimask', 'oulunpu'])
  - 659b6a62939a5f4082e8e6d7: 漏抽 6 个 (['imagenet21k', 'cifar10', 'inaturalist', 'imageneto', 'texture', 'imagenet1k'])

### datasets--策略v2--关键词全文匹配 (Layer 1)
- 漏抽论文数: 7
  - 5b1643ba8fbcbf6e5a9bc884: 漏抽 38 个 (['fgnet', 'ar', 'cplfw', 'rfw', 'guoetal.', 'casiafasd', 'nirvis2.0', 'umdfaces', 'fam', 'celebfaces+', 'replayattack', 'casiawebface', 'calfw', 'cufs', 'sllfw', 'facebook', 'feret', 'cfp', 'asianceleb', 'ytf', 'bosphorus', 'webcaricature', 'google', 'cufsf', 'cacd', 'umdfacesvideos', 'morph', 'msv1c', 'bu3dfe', 'msceleb1m', 'megaface', 'delfw', 'pasc', 'dfw', 'casiahfb', 'elfw', 'ijbc', 'frgcv2'])
  - 627c6cfe5aee126c0f83214c: 漏抽 3 个 (['msrvtt', 'wavcaps', 'mscoco'])
  - 62fdae3890e50fcafdd6387b: 漏抽 2 个 (['pascalvoc2012', 'cityscapes'])
  - 63b63fca90e50fcafd8f4461: 漏抽 1 个 (['siw'])
  - 659b6a62939a5f4082e8e6d7: 漏抽 6 个 (['imagenet21k', 'openimageo', 'inaturalist', 'imageneto', 'texture', 'imagenet1k'])

### datasets--策略v3--Gazetteer验证 (强语境正则+白名单+黑名单)
- 漏抽论文数: 10
  - 5b1643ba8fbcbf6e5a9bc884: 漏抽 39 个 (['ar', 'cplfw', 'rfw', 'guoetal.', 'casiafasd', 'nirvis2.0', 'fam', 'celebfaces+', 'replayattack', 'casiahfb', 'casiawebface', 'calfw', 'frgcv2', 'vggface2', 'cufs', 'facebook', 'sllfw', 'feret', 'cfp', 'asianceleb', 'ytf', 'bosphorus', 'webcaricature', 'google', 'cufsf', 'cacd', 'umdfacesvideos', 'ijba', 'msv1c', 'bu3dfe', 'megaface', 'delfw', 'pasc', 'dfw', 'umdfaces', 'elfw', 'ijbc', 'vggface', 'ijbb'])
  - 627c6cfe5aee126c0f83214c: 漏抽 7 个 (['macs', 'msrvtt', 'audiocaps', 'audioset', 'wavcaps', 'clotho', 'mscoco'])
  - 62fdae3890e50fcafdd6387b: 漏抽 2 个 (['pascalvoc2012', 'cityscapes'])
  - 6632f3d201d2a3fbfc5b36bb: 漏抽 1 个 (['jaad'])
  - 63b63fca90e50fcafd8f4461: 漏抽 6 个 (['marsv2', 'suhifimask', 'replayattack', 'siw', 'hifimask', 'oulunpu'])

## V3 提取统计
- 总候选数: 116
- Gazetteer匹配数: 23
- 黑名单过滤后: 23
- Gazetteer命中率: 19.8%
