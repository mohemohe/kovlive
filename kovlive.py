#! /usr/bin/env python
# coding:utf-8


import codecs
import math
import sys
import re
from logging import getLogger


class KovLang:
    def __init__(
        self,
        phrase_model_file: str,
        bigram_model_file: str,
        logger=None
    ) -> None:
        self.phrasemodel = self.load_phrase_model(phrase_model_file)
        self.unimodel, self.bimodel = self.load_bigram_model(bigram_model_file)
        # set logger
        self.logger = logger or getLogger(__file__)

    def load_phrase_model(
        self,
        modelfile: str
    ) -> dict:
        phrasemodel = {}
        with codecs.open(modelfile, 'r', 'utf-8') as f:
            for line in f:
                words, prob = line.rstrip().split("\t")
                prob = float(prob)
                w1, w2 = words.split(",")
                if w1 not in phrasemodel:
                    phrasemodel[w1] = {}
                phrasemodel[w1][w2] = prob
        return phrasemodel

    def load_bigram_model(
        self,
        modelfile: str
    ) -> (dict, dict):
        unimodel = {}
        bimodel = {}
        with codecs.open(modelfile, 'r', 'utf-8') as f:
            for line in f:
                words, prob = line.rstrip().split("\t")
                prob = float(prob)
                if " " in words:
                    w0, w1 = words.split(" ")
                    bimodel[(w0, w1)] = prob
                else:
                    unimodel[words] = prob
        return unimodel, bimodel

    def bigram_prob(
        self,
        w0: str,
        w1: str,
        lambda2: float=0.95,
        lambda1: float=0.95,
        unk_n: int=1e6,
        log: bool=True
    ) -> float:
        prob = (1 - lambda2) * (1 - lambda1) * (1 / unk_n)
        if (w0, w1) in self.bimodel:
            prob += lambda2 * self.bimodel[(w0, w1)]
        elif (w0, "*") in self.bimodel:
            prob += lambda2 * self.bimodel[(w0, "*")]

        if w1 in self.unimodel:
            prob += (1 - lambda2) * lambda1 * self.unimodel[w1]

        if log:
            return -math.log(prob)
        else:
            return prob

    def phrase_prob(
        self,
        p1: str,
        p2: str,
        lambda1: float=0.95,
        unk_n: int=1e6,
        log: bool=True
    ) -> float:

        prob = (1 - lambda1) * (1 / unk_n)
        if p1 in self.phrasemodel and p2 in self.phrasemodel[p1]:
            prob += lambda1 * self.phrasemodel[p1][p2]

        if log:
            return -math.log(prob)
        else:
            return prob

    def search(
        self,
        sent_without_symbol: [str],
        start_symbol: str="<s>",
        end_symbol: str="</s>",
        max_len=100,
        verbose: bool=False
    ) -> [str]:

        sent = [start_symbol] + sent_without_symbol + [end_symbol]
        sent_len = len(sent)
        best = [dict() for _ in range(sent_len)]
        best[0][(start_symbol, (0, 0))] = 0
        before_pos = [dict() for _ in range(sent_len)]

        for curpos in range(sent_len - 1):
            next_start = curpos + 1
            for next_end in range(
                    next_start,
                    min(sent_len, next_start+max_len)):
                next_phrase = ''.join(sent[next_start:next_end+1])
                next_word = sent[next_start]
                for (cur_phrase, (cur_start, cur_end)), prob in \
                        best[curpos].items():
                    # cur_word = sent[cur_end]
                    cur_key = (cur_phrase, (cur_start, cur_end))
                    conv_w0 = cur_phrase[-1]

                    # 候補にそのまま変換しないパタンがない場合
                    # このとき, next_phrase == next_word
                    if next_start == next_end and \
                            (next_phrase not in self.phrasemodel
                             or next_word not in
                                self.phrasemodel[next_phrase]):
                        conv_phrase = next_phrase
                        conv_w1 = conv_phrase[0]
                        next_key = (conv_phrase, (next_start, next_end))
                        next_prob = prob \
                            + self.bigram_prob(
                                conv_w0,
                                conv_w1) \
                            + self.phrase_prob(
                                next_phrase,
                                next_word)
                        if next_key in best[next_end]:
                            if best[next_end][next_key] >= next_prob:
                                best[next_end][next_key] = next_prob
                                before_pos[next_end][next_key] = cur_key
                        else:
                            best[next_end][next_key] = next_prob
                            before_pos[next_end][next_key] = cur_key
                    if next_phrase in self.phrasemodel:
                        for conv_phrase in self.phrasemodel[next_phrase]:
                            conv_w1 = conv_phrase[0]
                            next_key = (conv_phrase, (next_start, next_end))
                            next_prob = prob \
                                + self.bigram_prob(
                                    conv_w0,
                                    conv_w1) \
                                + self.phrase_prob(
                                    next_phrase,
                                    conv_phrase)
                            if next_key in best[next_end]:
                                if best[next_end][next_key] >= next_prob:
                                    best[next_end][next_key] = next_prob
                                    before_pos[next_end][next_key] = cur_key
                            else:
                                best[next_end][next_key] = next_prob
                                before_pos[next_end][next_key] = cur_key
        # verbose output
        if verbose:
            for i in range(1, sent_len):
                self.logger.debug("{}".format(sent[i]))
                for (key, (start, end)), prob in best[i].items():
                    before = before_pos[i][(key, (start, end))]
                    b_start, b_end = before[1]
                    b_key = before[0]
                    self.logger.debug(
                        "\t({}, {}) {} => {}: linked -> ({}, {}) {}".format(
                            start, end, key, round(prob, 4),
                            b_start, b_end, b_key
                            ))
                    word = ''.join(sent[start:end+1])
                    self.logger.debug(
                        "\t\t-log PP({} | {}) = {}".format(
                            key, word,
                            round(self.phrase_prob(
                                word,  # phrase
                                key,  # conv phrase
                                log=True), 4)
                            ))
                    self.logger.debug(
                        "\t\t-log BP({} | {}) = {}".format(
                            key[0],
                            b_key[-1],
                            round(self.bigram_prob(
                                b_key[-1],
                                key[0],
                                log=True), 4),
                            ))
        # search best
        ans = []
        ind = sent_len - 1
        start = ind
        end = ind
        min_val = float("inf")
        min_key = ""
        for (key, (_, _)), val in best[ind].items():
            if min_val > val:
                # print("{} => {}: {} => {}".format(
                #        min_key, key, min_val, val))
                min_key = key
                min_val = val
        ans.append(min_key)
        phrase, (start, end) = before_pos[ind][(min_key, (start, end))]
        ans.append(phrase)

        while end != 0:
            phrase, (start, end) = before_pos[end][(phrase, (start, end))]
            ans.append(phrase)

        ans.reverse()

        return ans

    def convert(
        self,
        sent_without_symbol: [str],
        start_symbol: str="<s>",
        end_symbol: str="</s>",
        max_len=100,
        verbose: bool=False
    ) -> str:
        ans = self.search(
            list(sent_without_symbol),
            verbose=verbose,
        )
        text = ''.join(ans)
        return re.sub(r"(^<s>|</s>$)", "", text)

    # alias
    ja2kov = convert


def test_ja2kov():
    import config

    def _test(*lst):
        kl = KovLang(
            config.PHRASE_MODEL,
            config.BIGRAM_MODEL)
        for frm, to in lst:
            assert kl.ja2kov(frm) == to

    _test(
        ["かぼちゃステーキかエナジードリンク飲みたい",
         "かぼちゃｽﾃｯｷかｴﾅﾖｰﾄﾞﾘﾝﾎﾟ飲みたいっ"],
        ["こんなところか",
         "こんなところかっ"],
        ["こんなところかっ",
         "こんなところかっ"],
        ["こんなところか。",
         "こんなところかっ"],
    )


if __name__ == '__main__':

    import config
    import argparse
    import os
    from logging import basicConfig, DEBUG

    if not (os.path.isfile(config.PHRASE_MODEL) and
            os.path.isfile(config.BIGRAM_MODEL)):
        print("Make first before executing kovlang.py", file=sys.stderr)
        sys.exit(1)

    # parse arg
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "file",
        nargs="?",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="input file: if absent, reads from stdin"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="show probability"
    )
    args = parser.parse_args()

    # logger
    logger = getLogger("kovlive")
    basicConfig(
        level=DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )

    # kovlang instance
    kl = KovLang(
        config.PHRASE_MODEL,
        config.BIGRAM_MODEL,
        logger
    )

    for line in (_.rstrip() for _ in args.file):
        conv_line = kl.ja2kov(line, verbose=args.verbose)
        print(conv_line)
