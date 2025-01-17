import os
import click
import glob
import pandas as pd

from rank_bm25 import BM25Okapi as BM25
import gensim
import gensim.downloader as api
import numpy as np
import logging

logging.basicConfig(level=logging.DEBUG)


class Retriever(object):
    def __init__(self, documents):
        self.corpus = documents
        self.bm25 = BM25(self.corpus)

    def query(self, tokenized_query, n=100):
        scores = self.bm25.get_scores(tokenized_query)
        best_docs = sorted(range(len(scores)), key=lambda i: -scores[i])[:n]
        return best_docs, [scores[i] for i in best_docs]


class Ranker(object):
    def __init__(self, query_embedding, document_embedding):
        self.query_embedding = query_embedding
        self.document_embedding = document_embedding

    def _create_mean_embedding(self, word_embeddings):
        return np.mean(
            word_embeddings,
            axis=0,
        )

    def _create_max_embedding(self, word_embeddings):
        return np.amax(
            word_embeddings,
            axis=0,
        )

    def _embed(self, tokens, embedding):
        word_embeddings = np.array([embedding[token] for token in tokens if token in embedding])
        mean_embedding = self._create_mean_embedding(word_embeddings)
        max_embedding = self._create_max_embedding(word_embeddings)
        embedding = np.concatenate([mean_embedding, max_embedding])
        unit_embedding = embedding / (embedding ** 2).sum() ** 0.5
        return unit_embedding

    def rank(self, tokenized_query, tokenized_documents):
        """
        Re-ranks a set of documents according to embedding distance
        """
        query_embedding = self._embed(tokenized_query, self.query_embedding)  # (E,)
        document_embeddings = np.array(
            [self._embed(document, self.document_embedding) for document in tokenized_documents])  # (N, E)
        scores = document_embeddings.dot(query_embedding)
        index_rankings = np.argsort(scores)[::-1]
        return index_rankings, np.sort(scores)[::-1]


class TSVDocumentReader(object):
    def __init__(self, path):
        self.path = path

    @property
    def corpus(self):
        df = pd.read_csv(self.path, delimiter="\t", header=None)
        return df[0].values.tolist()


class DocumentReader(object):
    def __init__(self, path):
        self.path = path

    @property
    def corpus(self):
        documents = []
        glob_path = os.path.join(self.path, "**")
        for document_path in glob.glob(glob_path, recursive=True):
            if os.path.isfile(document_path):
                with open(document_path, 'r', encoding='ISO-8859-1') as f:
                    documents.append(f.read())
        return documents


def tokenize(document):
    return list(gensim.utils.tokenize(document.lower()))


def show_scores(documents, scores, n=10):
    for i in range(min(n, len(scores))):
        print("======== RANK: {} | SCORE: {} =======".format(i + 1, scores[i]))
        print(documents[i])
    print("\n")


@click.command()
@click.option("--query", prompt="Search query", help="Search query")
def main(query):
    tokenized_query = tokenize(query)

    print("Reading documents.tsv...", end="")
    reader = TSVDocumentReader("documents.tsv")
    documents = [doc for doc in reader.corpus]
    print(" [DONE]")
    print("")

    print("Tokening documents...", end="")
    corpus = [list(gensim.utils.tokenize(doc.lower())) for doc in documents]
    print(" [DONE]")
    print("")

    retriever = Retriever(corpus)
    retrieval_indexes, retrieval_scores = retriever.query(tokenized_query)
    retrieved_documents = [documents[idx] for idx in retrieval_indexes]
    print("======== BM25 ========")
    print('Query: "{}"'.format(query))
    show_scores(retrieved_documents, retrieval_scores, 20)

    print("Loading glove embeddings...", end="")
    query_embedding = api.load('glove-wiki-gigaword-50')
    print(" [DONE]")
    print("")

    ranker = Ranker(query_embedding=query_embedding, document_embedding=query_embedding)
    tokenzed_retrieved_documents = [corpus[idx] for idx in retrieval_indexes]
    ranker_indexes, ranker_scores = ranker.rank(tokenized_query, tokenzed_retrieved_documents)
    reranked_documents = [retrieved_documents[idx] for idx in ranker_indexes]

    print("======== Embedding ========")
    print('Query: "{}"'.format(query))
    show_scores(reranked_documents, ranker_scores, 20)


if __name__ == "__main__":
    main()
