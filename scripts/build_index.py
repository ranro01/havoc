"""Embed runbooks + postmortems and save the FAISS index to ./index"""

from havoc import config
from havoc.retrieval import RunbookRetriever, get_embeddings

r = RunbookRetriever.build(config.data_dir(), get_embeddings())
r.save(config.index_dir())
print("index saved to", config.index_dir())
